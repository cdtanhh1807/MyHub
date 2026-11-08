"""SSE có replay từ ring MongoDB; một pump dùng chung, không polling DB cho từng thiết bị."""
import asyncio
import json
import logging
import time
from contextlib import suppress
from uuid import uuid4
from app.core.errors import AppError
from app.dtos.contracts import ResultDTO, StreamDTO
from app.dtos.sync import ChangeDTO
from app.models.records import ManagedStream

logger = logging.getLogger(__name__)


class SyncService:
    """Mongo giữ thứ tự nguyên tử; hàng đợi RAM có giới hạn và chỉ chứa tín hiệu nhỏ."""
    def __init__(self, settings, mongo, auth):
        """Phân vùng theo root cấu hình, không nhận root tùy ý từ trình duyệt."""
        self.settings, self.mongo, self.auth = settings, mongo, auth
        self.root, self.epoch = settings.google_drive_root_folder_id, uuid4().hex
        self.clients, self.wake, self.task = {}, asyncio.Event(), None
        self.latest = {'epoch': self.epoch, 'sequence': 0, 'events': []}
        self.degraded, self.closed = False, False
        self.activity = None

    @staticmethod
    def cursor(snapshot):
        """Cursor trỏ tới counter và epoch của một bản cập nhật nguyên tử trong Mongo."""
        return f"{snapshot['epoch']}:{snapshot['sequence']}"

    async def snapshot(self):
        """Đọc một document ring có giới hạn, không quét collection hoặc Drive."""
        return await self.mongo.get('sync_log', self.root) or self.latest

    async def start(self):
        """Sau startup/deploy phát reset để bắt cả thay đổi do restore/config ngoài ứng dụng."""
        await self.publish(ChangeDTO(kind='reset'))
        initial = await self.snapshot()
        self.latest = {'epoch': initial['epoch'], 'sequence': initial['sequence'], 'events': []}
        self.wake.clear()
        self.task = asyncio.create_task(self.pump())

    async def close(self):
        """Đóng pump và đánh thức stream để shutdown không giữ lại hàng đợi/DB pool."""
        self.closed = True
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        for entry in list(self.clients.values()):
            self.offer(entry['queue'], None)

    async def publish(self, change):
        """Ghi tín hiệu sau mutation thật; lỗi sync không biến một lần ghi Drive thành lỗi giả."""
        try:
            event = change.model_dump(exclude_none=True)
            if self.degraded:
                event = ChangeDTO(kind='reset').model_dump(exclude_none=True)
            if len(json.dumps(event)) > 8192:
                event = ChangeDTO(kind='reset').model_dump(exclude_none=True)
            await self.mongo.sync_append(self.root, self.epoch, event, self.settings.sync_history_size)
            self.degraded = False
        except Exception:
            # Không log exception chứa Mongo URI; đối soát Drive/reconnect sẽ sửa cache bị bỏ lỡ.
            if not self.degraded:
                logger.warning('Sync event storage unavailable; clients will reconcile.')
            self.degraded = True
        self.wake.set()
        return not self.degraded

    async def changed(self, **values):
        """Service nghiệp vụ tạo tín hiệu có schema, không suy luận mutation từ HTTP path/body."""
        if values.get('kind') == 'connection' and self.activity:
            self.activity()
        return await self.publish(ChangeDTO(**values))

    async def file_changed(self, workspace_id, file, *, parent_ids=None, workspace_ids=None, tree=False, trash=False):
        """Chuẩn hóa tín hiệu file cho mọi service; source/target đều được thông báo khi di chuyển."""
        await self.changed(workspace_ids=list(dict.fromkeys([workspace_id, *(workspace_ids or [])])),
            parent_ids=list(dict.fromkeys([*file.get('parents', []), *(parent_ids or [])])),
            file_ids=[file['id']], tree=tree, trash=trash)

    @staticmethod
    def offer(queue, value):
        """Client chậm không chặn writer; khi đầy thay backlog bằng reset thay vì tăng RAM vô hạn."""
        if queue.full():
            while not queue.empty():
                queue.get_nowait()
            value = None if value is None else {'reset': True, 'snapshot': {
                'epoch': value['snapshot']['epoch'], 'sequence': value['snapshot']['sequence'], 'events': []}}
        queue.put_nowait(value)

    async def pump(self):
        """Gộp thay đổi 150 ms; chỉ một lần đọc Mongo cho tất cả stream trong worker."""
        while not self.closed:
            try:
                # Không có subscriber thì không đọc DB định kỳ; publish/subscriber mới sẽ đánh thức.
                if self.clients:
                    with suppress(TimeoutError):
                        await asyncio.wait_for(self.wake.wait(), timeout=30)
                else:
                    await self.wake.wait()
                self.wake.clear()
                if not self.clients:
                    continue
                await asyncio.sleep(.15)
                if self.degraded:
                    await self.publish(ChangeDTO(kind='reset'))
                    # publish đánh thức pump; bỏ wake tự tạo để lỗi DB không gây loop 150 ms.
                    self.wake.clear()
                snapshot = await self.snapshot()
                if self.degraded:
                    snapshot = {**snapshot, 'force_reset': True}
                if self.cursor(snapshot) != self.cursor(self.latest) or self.degraded:
                    # Queue chỉ giữ delta kể từ batch trước, không giữ cả ring cho từng client.
                    previous = self.latest
                    events = snapshot.get('events', [])
                    start = max(0, previous['sequence'] - (snapshot['sequence'] - len(events))) if previous['epoch'] == snapshot['epoch'] else 0
                    batch = {**snapshot, 'events': events[start:]}
                    self.latest = {'epoch': snapshot['epoch'], 'sequence': snapshot['sequence'], 'events': []}
                    for entry in list(self.clients.values()):
                        self.offer(entry['queue'], {'snapshot': batch, 'reset': self.degraded or snapshot['sequence'] < previous['sequence']})
            except asyncio.CancelledError:
                raise
            except Exception:
                # Backoff dùng chung, không tạo retry loop độc lập cho mỗi kết nối.
                await asyncio.sleep(5)

    async def status(self):
        """Endpoint tương thích/fallback thưa; không chứa ID phiên, channel token hoặc Redis URI."""
        snapshot = await self.snapshot()
        return ResultDTO(data={'revision': self.cursor(snapshot), 'transport': 'sse'})

    def subscribe(self, user_id, device_id, claims, cursor):
        """Giới hạn kết nối trước khi gửi HTTP headers, để trả 429 đúng cho client."""
        if sum(entry['user'] == user_id for entry in self.clients.values()) >= self.settings.sync_max_connections_per_user:
            raise AppError('sync_connection_limit', 429)
        idle = not self.clients
        key, queue = uuid4().hex, asyncio.Queue(maxsize=4)
        self.clients[key] = {'user': user_id, 'queue': queue}
        self.wake.set()
        if idle and self.activity:
            self.activity()
        async def close():
            """Thu hồi slot kể cả client ngắt trước byte đầu tiên của stream."""
            self.clients.pop(key, None)
        return StreamDTO(content=ManagedStream(self.stream(key, queue, user_id, device_id, claims, cursor), close),
            headers={'Content-Type': 'text/event-stream; charset=utf-8', 'X-Accel-Buffering': 'no'})

    @staticmethod
    def frame(event, data, cursor=''):
        """Một frame SSE UTF-8; json escaping ngăn newline/header injection."""
        prefix = f'id: {cursor}\n' if cursor else ''
        return f'{prefix}event: {event}\ndata: {json.dumps(data, separators=(",", ":"))}\n\n'.encode()

    def replay(self, snapshot, cursor, user_id, device_id, session_id):
        """Replay có giới hạn; cursor hết hạn/khác epoch/future sẽ yêu cầu đọc lại snapshot API."""
        head, sequence = self.cursor(snapshot), snapshot['sequence']
        events = snapshot.get('events', [])
        try:
            epoch, position = cursor.split(':')
            position = int(position)
            valid = epoch == snapshot['epoch'] and sequence - len(events) <= position <= sequence
        except (ValueError, AttributeError):
            valid, position = False, 0
        if not valid or snapshot.get('force_reset'):
            return 'reset', [], head
        selected = []
        for index, change in enumerate(events, start=sequence - len(events) + 1):
            if index <= position:
                continue
            if change.get('session_id'):
                if change['session_id'] == session_id:
                    return 'auth_expired', [], head
                continue
            if change.get('user_id') and change['user_id'] != user_id:
                continue
            if change.get('device_id') and change['device_id'] != device_id:
                continue
            if change['kind'] == 'reset':
                return 'reset', [], head
            selected.append({k: v for k, v in change.items() if k not in ('user_id', 'device_id', 'session_id')})
        if len(json.dumps(selected)) > 256 * 1024:
            return 'reset', [], head
        return 'changes', selected, head

    async def stream(self, key, queue, user_id, device_id, claims, cursor):
        """Heartbeat nhẹ; kiểm tra phiên mỗi phút và đóng đúng lúc JWT hết hạn, không lưu token."""
        checked = time.monotonic()
        first = True
        try:
            snapshot = await self.snapshot()
            while not self.closed:
                if claims['exp'] <= time.time():
                    yield self.frame('auth_expired', {})
                    return
                if time.monotonic() - checked >= 60:
                    try:
                        await self.auth.user_for_session(claims['sid'])
                    except AppError:
                        yield self.frame('auth_expired', {})
                        return
                    except Exception:
                        yield self.frame('retry', {})
                        return
                    checked = time.monotonic()
                event, changes, next_cursor = self.replay(snapshot, cursor, user_id, device_id, claims['sid'])
                if event != 'changes' or next_cursor != cursor:
                    yield self.frame(event, {'changes': changes}, next_cursor)
                elif first:
                    yield self.frame('ready', {}, next_cursor)
                first = False
                if snapshot.get('force_reset'):
                    snapshot = {**snapshot, 'force_reset': False}
                cursor = next_cursor
                # Giải phóng ring/delta trước khi chờ heartbeat, tránh giữ bản sao lịch sử mỗi stream.
                snapshot = {'epoch': snapshot['epoch'], 'sequence': snapshot['sequence'], 'events': []}
                if event == 'auth_expired':
                    return
                remaining = claims['exp'] - time.time()
                if remaining <= 0:
                    yield self.frame('auth_expired', {})
                    return
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=min(self.settings.sync_heartbeat_seconds, remaining))
                    if item is None:
                        return
                    epoch, position = cursor.split(':')
                    if not item.get('reset') and item['snapshot']['epoch'] == epoch and item['snapshot']['sequence'] <= int(position):
                        continue
                    snapshot = item['snapshot']
                    if item.get('reset'):
                        snapshot = {**snapshot, 'force_reset': True}
                except TimeoutError:
                    yield b': heartbeat\n\n'
        except asyncio.CancelledError:
            raise
        except Exception:
            # Sau khi headers đã gửi, không để lỗi DB làm lộ traceback trong stream/log ASGI.
            yield self.frame('retry', {})
        finally:
            self.clients.pop(key, None)
