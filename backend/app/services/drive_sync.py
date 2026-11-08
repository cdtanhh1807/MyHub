"""Một worker đọc Drive Changes cho toàn bộ thiết bị; webhook chỉ đánh thức và ACK nhanh."""
import asyncio
import hashlib
import json
import logging
import random
import secrets
import time
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from app.core.errors import AppError
from app.utils.files import FOLDER

logger = logging.getLogger(__name__)


class DriveSyncService:
    """Cursor/kênh/index được lưu theo root; không crawl toàn bộ Drive hoặc sao chép nội dung."""
    def __init__(self, settings, mongo, drive, scope, sync):
        """Dùng pool/repository hiện có, không tạo daemon, container hoặc scheduler bên ngoài."""
        self.settings, self.mongo, self.drive, self.scope, self.sync = settings, mongo, drive, scope, sync
        self.root, self.wake, self.task = settings.google_drive_root_folder_id, asyncio.Event(), None
        self.retry = 30
        self.channels, self.channels_refreshed = {}, 0

    def start(self):
        """Local dùng delta khi có subscriber; production có thể bật webhook HTTPS bằng env."""
        if self.settings.drive_sync_enabled:
            self.task = asyncio.create_task(self.run())

    async def close(self):
        """Giữ kênh webhook qua restart, chỉ dừng task HTTP/DB hiện tại để không bỏ lỡ delta."""
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task

    async def run(self):
        """Đối soát mỗi 5 phút hoặc khi webhook đánh thức; backoff chung khi Google/DB lỗi."""
        while True:
            delay = self.settings.drive_sync_interval_seconds
            try:
                if self.settings.drive_webhook_enabled or self.sync.clients:
                    await self.reconcile()
                self.retry = 30
            except asyncio.CancelledError:
                raise
            except Exception:
                # Chỉ ghi thông báo chung, không log URL, token OAuth hay nội dung upstream.
                delay = self.retry + random.uniform(0, self.retry * .2)
                if self.retry == 30:
                    logger.warning('Drive change reconciliation unavailable; retrying with backoff.')
                self.retry = min(self.retry * 2, 900)
            with suppress(TimeoutError):
                await asyncio.wait_for(self.wake.wait(), timeout=delay)
            self.wake.clear()

    async def reconcile(self):
        """Đọc delta theo trang, phát tín hiệu trước khi tiến cursor để lỗi có thể replay an toàn."""
        state = await self.mongo.get('drive_sync_state', self.root) or {}
        if not state.get('cursor'):
            cursor = await self.drive.changes_start()
            await self.mongo.put('drive_sync_state', self.root, {'cursor': cursor})
            state['cursor'] = cursor
            await self.sync.changed(kind='reset')
        if self.settings.drive_webhook_enabled:
            try:
                await self.ensure_channel(state)
            except Exception:
                # Webhook chưa truy cập được vẫn tiếp tục đối soát delta, không làm hỏng fallback.
                logger.warning('Drive webhook renewal unavailable; periodic reconciliation remains active.')
        # Clear dirty trước khi gọi Google: notification đến trong lúc đọc vẫn được giữ cho lượt sau.
        await self.mongo.put('drive_sync_state', self.root, {'dirty': False})
        cursor = state['cursor']
        for _ in range(5):
            try:
                page = await self.drive.changes_page(cursor)
            except AppError as error:
                if error.status != 410 and error.code != 'drive_error_410':
                    raise
                # Cursor Google bị thu hồi/hết hiệu lực: reset cache, bắt đầu từ mốc mới.
                await self.mongo.put('drive_sync_state', self.root, {'cursor': await self.drive.changes_start()})
                await self.sync.changed(kind='reset')
                return
            await self.process_changes(page.get('changes', []))
            next_cursor = page.get('nextPageToken') or page.get('newStartPageToken')
            if not next_cursor:
                raise AppError('invalid_drive_changes', 502)
            await self.mongo.put('drive_sync_state', self.root, {'cursor': next_cursor})
            cursor = next_cursor
            if not page.get('nextPageToken'):
                break
        else:
            # Feed lớn được chia lượt để không giữ event loop/Drive API liên tục.
            self.wake.set()
        latest = await self.mongo.get('drive_sync_state', self.root) or {}
        if latest.get('dirty'):
            self.wake.set()

    @staticmethod
    def signature(file):
        """Hash metadata cần đồng bộ để bỏ notification trùng mà không lưu nội dung file."""
        fields = {key: file.get(key) for key in ('name', 'mimeType', 'parents', 'version', 'trashed', 'permissions')}
        return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()

    async def locate(self, file, cache):
        """Lần theo cha có cache theo trang; chỉ chấp nhận cây thuộc root, loại system/shortcut/cycle."""
        current, seen = file, set()
        for _ in range(128):
            if current['id'] in seen or self.scope.system(current) or current['mimeType'] == 'application/vnd.google-apps.shortcut':
                return None
            seen.add(current['id'])
            parents = current.get('parents', [])
            if parents == [self.root]:
                return current['id'] if current['mimeType'] == FOLDER else None
            if len(parents) != 1 or current['id'] == self.root:
                return None
            if parents[0] not in cache:
                try:
                    cache[parents[0]] = await self.drive.get(parents[0])
                except AppError as error:
                    if error.status in (403, 404):
                        return None
                    raise
            current = cache[parents[0]]
        return None

    async def process_changes(self, changes):
        """Gom một trang thành một event; index TTL giúp nhận ra xóa/move-out mà không crawl Drive."""
        keys = [f"{self.root}:{item['fileId']}" for item in changes]
        known = await self.mongo.drive_index_get(keys) if keys else {}
        cache = {item['fileId']: item['file'] for item in changes if item.get('file')}
        workspaces, parents, files, records = set(), set(), set(), []
        reset, tree, trash, workspace_change, connection = False, False, False, False, False
        for item in changes:
            file_id, file = item['fileId'], item.get('file')
            if file_id == self.root:
                connection = True
                continue
            old = known.get(f'{self.root}:{file_id}', {})
            workspace = await self.locate(file, cache) if file and not item.get('removed') else None
            if not workspace and not old.get('workspace'):
                # Tombstone thiếu metadata không thể biết phạm vi: reset không chứa ID riêng tư.
                reset |= bool(item.get('removed'))
                continue
            signature = self.signature(file) if file else 'removed'
            if workspace == old.get('workspace') and signature == old.get('signature'):
                continue
            workspaces.update(value for value in (workspace, old.get('workspace')) if value)
            parents.update(old.get('parents', []))
            parents.update(file.get('parents', []) if file else [])
            files.add(file_id)
            is_folder = file.get('mimeType') == FOLDER if file else old.get('folder', False)
            tree |= is_folder
            trash |= bool(item.get('removed') or (file and file.get('trashed')) or old.get('trashed'))
            workspace_change |= file_id in workspaces
            records.append({'_id': f'{self.root}:{file_id}', 'workspace': workspace,
                'parents': file.get('parents', []) if workspace else [], 'signature': signature,
                'folder': is_folder, 'trashed': bool(file and file.get('trashed')),
                'expires_at': datetime.now(timezone.utc) + timedelta(days=7)})
        if connection:
            stored = await self.sync.changed(kind='connection')
        elif reset or max(len(workspaces), len(parents), len(files)) > 100:
            stored = await self.sync.changed(kind='reset')
        elif files:
            stored = await self.sync.changed(kind='workspaces' if workspace_change else 'files', workspace_ids=sorted(workspaces),
                parent_ids=sorted(parents), file_ids=sorted(files), tree=tree, trash=trash)
        else:
            stored = True
        if not stored:
            # Không tiến cursor Drive khi event chưa bền vững trong DB, lượt sau sẽ đọc lại.
            raise AppError('sync_storage_unavailable', 503)
        # Chỉ cập nhật index sau khi phát event; crash giữa hai bước chỉ tạo event trùng, không mất delta.
        await self.mongo.drive_index_put(records)

    async def ensure_channel(self, state):
        """Thay kênh trước hạn 6 giờ; lưu pending trước watch để nhận được sync callback đến sớm."""
        now = time.time()
        address = self.settings.backend_url.rstrip('/') + '/api/v1/sync/drive/webhook'
        channels = [row for row in state.get('channels', []) if row.get('expires', 0) > now]
        if any(row.get('resource_id') and row.get('address') == address and row['expires'] > now + 21600 for row in channels):
            return
        channel_id, token = uuid4().hex, secrets.token_urlsafe(32)
        pending = {'id': channel_id, 'token_hash': hashlib.sha256(token.encode()).hexdigest(), 'resource_id': '',
            'address': address, 'expires': now + 600, 'last_message': 0}
        active = [row for row in channels if row.get('resource_id')][-1:]
        await self.mongo.put('drive_sync_state', self.root, {'channels': [*active, pending]})
        self.channels = {row['id']: row for row in [*active, pending]}
        self.channels_refreshed = time.monotonic()
        result = await self.drive.changes_watch(state['cursor'], {'id': channel_id, 'type': 'web_hook', 'address': address,
            'token': token, 'expiration': int((now + 6 * 86400) * 1000)})
        if result.get('id') != channel_id or not result.get('resourceId'):
            raise AppError('invalid_drive_watch', 502)
        # Giữ số thông báo đã nhận trong lúc watch đang chờ, không ghi đè last_message bằng 0.
        await self.mongo.drive_channel_ready(self.root, channel_id, result['resourceId'],
            min(float(result.get('expiration', (now + 3600) * 1000)) / 1000, now + 7 * 86400))
        self.channels[channel_id].update(resource_id=result['resourceId'],
            expires=min(float(result.get('expiration', (now + 3600) * 1000)) / 1000, now + 7 * 86400))
        for old in active:
            try:
                await self.drive.stop_watch(old['id'], old['resource_id'])
            except Exception:
                pass

    async def notification(self, dto):
        """Kiểm tra bí mật ngẫu nhiên/kênh/resource/expiry, chống replay rồi ACK; không gọi Google tại đây."""
        if not self.settings.drive_sync_enabled or not self.settings.drive_webhook_enabled:
            raise AppError('not_found', 404)
        # Cache chỉ hai channel hash tối đa một phút: token sai/trùng không tạo truy vấn DB mỗi request.
        if time.monotonic() - self.channels_refreshed >= 60:
            state = await self.mongo.get('drive_sync_state', self.root) or {}
            self.channels = {row['id']: row for row in state.get('channels', [])}
            self.channels_refreshed = time.monotonic()
        channel = self.channels.get(dto.channel_id)
        token_hash = hashlib.sha256(dto.token.encode()).hexdigest()
        if (not channel or channel['expires'] <= time.time() or not secrets.compare_digest(channel['token_hash'], token_hash)
                or (channel['resource_id'] and channel['resource_id'] != dto.resource_id)
                or (not channel['resource_id'] and dto.state != 'sync')):
            raise AppError('invalid_drive_notification', 403)
        if dto.state not in ('sync', 'change', 'changed'):
            return
        if dto.message_number <= channel.get('last_message', 0):
            return
        if await self.mongo.drive_notification(self.root, dto.channel_id, dto.message_number):
            channel['last_message'] = dto.message_number
            self.wake.set()
