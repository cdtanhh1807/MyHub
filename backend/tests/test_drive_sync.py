"""Kiểm tra delta Drive/webhook bằng HTTP/repository giả, bao gồm callback đến trước watch response."""
import copy
import hashlib
import time
import pytest
from app.core.errors import AppError
from app.dtos.sync import DriveNotificationRequest
from app.services.sync import SyncService
from app.services.drive_sync import DriveSyncService


def monitor(settings, container):
    """Ghép Service thật nhưng không start background task, mỗi test tự điều khiển các bước."""
    sync = SyncService(settings, container.mongo, container.auth)
    return DriveSyncService(settings, container.mongo, container.drive, container.scope, sync)


async def test_scope_filtering_move_out_tombstones_and_duplicate_delta(settings, container):
    """Chỉ phát ID trong root; chuyển ra ngoài/xóa dùng vị trí trước đó và tombstone lạ reset an toàn."""
    service = monitor(settings, container)
    drive = container.drive
    await service.process_changes([{'fileId': key, 'file': copy.deepcopy(drive.files[key])} for key in ('text', 'external_file', 'system_file')])
    log = await container.mongo.get('sync_log', 'root')
    assert log['events'][-1]['file_ids'] == ['text']
    assert log['events'][-1]['workspace_ids'] == ['ws']
    sequence = log['sequence']
    await service.process_changes([{'fileId': 'text', 'file': copy.deepcopy(drive.files['text'])}])
    assert (await container.mongo.get('sync_log', 'root'))['sequence'] == sequence
    moved = {**drive.files['text'], 'parents': ['outside'], 'version': '2'}
    await service.process_changes([{'fileId': 'text', 'file': moved}])
    event = (await container.mongo.get('sync_log', 'root'))['events'][-1]
    assert event['workspace_ids'] == ['ws'] and event['file_ids'] == ['text']
    await service.process_changes([{'fileId': 'unknown-private-id', 'removed': True}])
    event = (await container.mongo.get('sync_log', 'root'))['events'][-1]
    assert event['kind'] == 'reset' and 'unknown-private-id' not in str(event)


async def test_webhook_security_early_callback_deduplication_and_renewal(settings, container, monkeypatch):
    """Token/kênh/resource/expiry được đối chiếu; callback sớm và trùng không bị mất dirty/counter."""
    settings = settings.model_copy(update={'backend_url': 'https://myhub.example.com', 'drive_webhook_enabled': True})
    service = monitor(settings, container)
    issued, stopped = [], []
    async def watch(cursor, channel):
        """Google có thể gửi sync callback ngay trước lúc POST watch trả về."""
        issued.append(channel)
        await service.notification(DriveNotificationRequest(channel_id=channel['id'], token=channel['token'], resource_id='resource', state='sync', message_number=1))
        return {'id': channel['id'], 'resourceId': 'resource', 'expiration': str(int((time.time() + 86400) * 1000))}
    async def stop(channel_id, resource):
        """Ghi nhận kênh cũ được dừng sau khi kênh mới sẵn sàng."""
        stopped.append(channel_id)
    monkeypatch.setattr(container.drive, 'changes_watch', watch, raising=False)
    monkeypatch.setattr(container.drive, 'stop_watch', stop, raising=False)
    await container.mongo.put('drive_sync_state', 'root', {'cursor': 'cursor'})
    await service.ensure_channel({'cursor': 'cursor'})
    state = await container.mongo.get('drive_sync_state', 'root')
    assert state['dirty'] and state['channels'][-1]['last_message'] == 1
    assert 'token' not in state['channels'][-1]
    service.wake.clear()
    channel = issued[-1]
    values = dict(channel_id=channel['id'], token=channel['token'], resource_id='resource', state='changed', message_number=2)
    await service.notification(DriveNotificationRequest(**values))
    assert service.wake.is_set()
    service.wake.clear()
    await service.notification(DriveNotificationRequest(**values))
    assert not service.wake.is_set()
    for invalid in ({'token': 'wrong'}, {'resource_id': 'wrong'}, {'channel_id': 'wrong'}):
        with pytest.raises(AppError) as error:
            await service.notification(DriveNotificationRequest(**{**values, **invalid, 'message_number': 3}))
        assert error.value.status == 403
    state = await container.mongo.get('drive_sync_state', 'root')
    await service.ensure_channel(state)
    assert len(issued) == 1
    state['channels'][-1]['expires'] = time.time() + 100
    await container.mongo.put('drive_sync_state', 'root', state)
    await service.ensure_channel(state)
    assert len(issued) == 2 and stopped == [channel['id']]


async def test_pagination_cursor_recovery_and_webhook_failure_does_not_disable_fallback(settings, container, monkeypatch):
    """Watch lỗi vẫn đọc delta; phân trang/410 cập nhật cursor chỉ sau khi xử lý thành công."""
    settings = settings.model_copy(update={'backend_url': 'https://myhub.example.com', 'drive_webhook_enabled': True})
    service = monitor(settings, container)
    calls = []
    async def start():
        """Mốc feed mới không cần đọc danh sách file hiện có."""
        return 'start'
    async def watch(*args):
        """Webhook chưa truy cập được trong lúc cấu hình production lần đầu."""
        raise AppError('watch_unavailable', 502)
    async def page(cursor):
        """Mỗi trang giữ token riêng, trang cuối trả newStartPageToken."""
        calls.append(cursor)
        if cursor == 'expired':
            raise AppError('drive_error_410', 410)
        if cursor == 'start':
            return {'changes': [{'fileId': 'text', 'file': container.drive.files['text']}], 'nextPageToken': 'page2'}
        return {'changes': [], 'newStartPageToken': 'next'}
    monkeypatch.setattr(container.drive, 'changes_start', start, raising=False)
    monkeypatch.setattr(container.drive, 'changes_watch', watch, raising=False)
    monkeypatch.setattr(container.drive, 'changes_page', page, raising=False)
    await service.reconcile()
    assert calls == ['start', 'page2']
    assert (await container.mongo.get('drive_sync_state', 'root'))['cursor'] == 'next'
    await container.mongo.put('drive_sync_state', 'root', {'cursor': 'expired'})
    await service.reconcile()
    assert (await container.mongo.get('drive_sync_state', 'root'))['cursor'] == 'start'


async def test_delta_cursor_does_not_advance_when_signal_cannot_be_saved(settings, container, monkeypatch):
    """Mất DB sau khi đọc Google phải để cursor cũ cho lần retry, không nuốt mất sự kiện."""
    service = monitor(settings, container)
    await container.mongo.put('drive_sync_state', 'root', {'cursor': 'old'})
    async def page(cursor):
        """Một delta trong Workspace hợp lệ."""
        return {'changes': [{'fileId': 'text', 'file': container.drive.files['text']}], 'newStartPageToken': 'new'}
    async def fail(*args):
        """Chỉ ring lỗi; đọc state/cursor vẫn hoạt động để kiểm tra quyết định commit."""
        raise RuntimeError('storage unavailable')
    monkeypatch.setattr(container.drive, 'changes_page', page, raising=False)
    monkeypatch.setattr(container.mongo, 'sync_append', fail)
    with pytest.raises(AppError):
        await service.reconcile()
    assert (await container.mongo.get('drive_sync_state', 'root'))['cursor'] == 'old'
