"""Kiểm tra SSE replay, tài nguyên, lỗi và xác thực bằng DB giả, không dùng dịch vụ thật."""
import asyncio
import json
import time
import math
import jwt
import pytest
from app.core.errors import AppError
from app.services.sync import SyncService


async def make_sync(settings, container):
    """Dùng kho fake riêng của mỗi test và pump thật để kiểm tra batching thực tế."""
    sync = SyncService(settings, container.mongo, container.auth)
    await sync.start()
    return sync


async def test_replay_bounds_and_private_audiences(settings, container):
    """Cursor cũ/future/epoch khác reset; preference không lọt sang máy hoặc tài khoản khác."""
    sync = await make_sync(settings.model_copy(update={'sync_history_size': 32}), container)
    try:
        old = (await sync.status()).data['revision']
        for _ in range(40):
            await sync.changed(workspace_ids=['ws'], parent_ids=['sub'], file_ids=['text'])
        snapshot = await sync.snapshot()
        assert len(snapshot['events']) == 32
        assert sync.replay(snapshot, old, 'owner', 'A', 'session')[0] == 'reset'
        assert sync.replay(snapshot, snapshot['epoch'] + ':99999', 'owner', 'A', 'session')[0] == 'reset'
        start = sync.cursor(snapshot)
        await sync.changed(kind='preferences', user_id='owner', device_id='A')
        await sync.changed(kind='preferences', user_id='owner', device_id='B')
        await sync.changed(kind='preferences', user_id='someone-else', device_id='A')
        event, changes, _ = sync.replay(await sync.snapshot(), start, 'owner', 'A', 'session')
        assert event == 'changes' and len(changes) == 1
        assert 'user_id' not in changes[0] and 'device_id' not in changes[0]
        await sync.changed(kind='session', session_id='other-session')
        assert sync.replay(await sync.snapshot(), start, 'owner', 'A', 'session')[0] == 'changes'
        await sync.changed(kind='session', session_id='session')
        assert sync.replay(await sync.snapshot(), start, 'owner', 'A', 'session')[0] == 'auth_expired'
    finally:
        await sync.close()


async def test_one_database_read_fans_out_to_one_hundred_clients(settings, container, monkeypatch):
    """100 subscriber dùng một pump; 20 mutation dồn trong một batch không tạo 100 lần đọc DB."""
    sync = await make_sync(settings.model_copy(update={'sync_max_connections_per_user': 100}), container)
    streams = []
    try:
        for _ in range(100):
            streams.append(sync.subscribe('owner', 'A', {'sid': 'fake-session', 'exp': time.time() + 600}, '').content)
        await asyncio.gather(*(anext(stream) for stream in streams))
        await asyncio.sleep(.2)
        reads = 0
        original = container.mongo.get
        async def counted(collection, key):
            """Đo số lần pump đọc ring, không giả định chi phí phần cứng VPS."""
            nonlocal reads
            if collection == 'sync_log':
                reads += 1
            return await original(collection, key)
        monkeypatch.setattr(container.mongo, 'get', counted)
        for number in range(20):
            await sync.changed(workspace_ids=['ws'], file_ids=[f'file{number}'])
        frames = await asyncio.wait_for(asyncio.gather(*(anext(stream) for stream in streams)), 3)
        assert reads == 1
        assert all(b'file19' in frame for frame in frames)
        assert all(entry['queue'].qsize() <= 4 for entry in sync.clients.values())
    finally:
        await asyncio.gather(*(stream.aclose() for stream in streams))
        await sync.close()


async def test_limit_slow_consumer_and_early_disconnect(settings, container):
    """Ngắt trước byte đầu vẫn trả slot; client chậm chuyển sang reset và giữ RAM có giới hạn."""
    sync = await make_sync(settings.model_copy(update={'sync_max_connections_per_user': 1}), container)
    try:
        dto = sync.subscribe('owner', 'A', {'sid': 'session', 'exp': time.time() + 600}, '')
        with pytest.raises(AppError) as error:
            sync.subscribe('owner', 'A', {'sid': 'session', 'exp': time.time() + 600}, '')
        assert error.value.status == 429
        entry = next(iter(sync.clients.values()))
        for _ in range(10):
            sync.offer(entry['queue'], {'snapshot': sync.latest})
        assert entry['queue'].qsize() <= 4
        values = [entry['queue'].get_nowait() for _ in range(entry['queue'].qsize())]
        assert any(row.get('reset') for row in values)
        await dto.content.aclose()
        assert not sync.clients
    finally:
        await sync.close()


async def test_expired_token_closes_stream_and_releases_slot(settings, container):
    """Stream không sống vượt thời hạn JWT dù không có sự kiện dữ liệu nào."""
    sync = await make_sync(settings, container)
    try:
        stream = sync.subscribe('owner', 'A', {'sid': 'session', 'exp': time.time() + .03}, '').content
        frames = []
        async for frame in stream:
            frames.append(frame)
        assert any(b'auth_expired' in frame for frame in frames)
        assert not sync.clients
    finally:
        await sync.close()


async def test_failed_signal_does_not_undo_drive_write_and_recovers_with_reset(settings, container, monkeypatch, caplog):
    """DB sync lỗi không báo ghi file thất bại; khi hồi phục phát reset để sửa cache bỏ lỡ."""
    from app.dtos.contracts import FolderRequest
    sync = await make_sync(settings, container)
    container.files.sync = sync
    original = container.mongo.sync_append
    async def fail(*args):
        """Mô phỏng lỗi có thông tin riêng tư, không được đưa nguyên exception vào log."""
        raise RuntimeError('private-database-uri-must-not-be-logged')
    try:
        monkeypatch.setattr(container.mongo, 'sync_append', fail)
        result = await container.files.rename(FolderRequest(workspace_id='ws', file_id='text', name='saved.py'))
        assert result.name == 'saved.py' and sync.degraded
        assert 'private-database-uri' not in caplog.text
        monkeypatch.setattr(container.mongo, 'sync_append', original)
        await sync.changed(workspace_ids=['ws'], file_ids=['other'])
        assert not sync.degraded
        assert (await sync.snapshot())['events'][-1]['kind'] == 'reset'
    finally:
        await sync.close()


async def test_restarts_keep_cursor_history_and_reset_cache(settings, container):
    """Log bền vững không phụ thuộc RAM của một worker, reset mới được replay sau restart."""
    first = await make_sync(settings, container)
    await first.changed(workspace_ids=['ws'], file_ids=['text'])
    cursor = (await first.status()).data['revision']
    await first.close()
    second = await make_sync(settings, container)
    try:
        snapshot = await second.snapshot()
        assert snapshot['epoch'] == cursor.split(':')[0]
        assert second.replay(snapshot, cursor, 'owner', 'A', 'session')[0] == 'reset'
    finally:
        await second.close()


def test_http_stream_headers_expiry_and_authentication(settings, container):
    """Qua ASGI thật: chỉ Bearer hợp lệ được mở SSE; JWT hết hạn đóng body và thu hồi slot."""
    from fastapi.testclient import TestClient
    from app.main import create_app
    user = {'id': 'owner', 'name': 'Owner', 'identity': 'owner@example.com', 'provider': 'google'}
    asyncio.run(container.mongo.put('users', 'owner', user))
    access = asyncio.run(container.auth.create_session(user)).data['access_token']
    claims = container.auth.claims(access)
    app = create_app(settings, container)
    with TestClient(app) as client:
        assert client.get('/api/v1/sync/events').status_code == 401
        assert client.get('/api/v1/sync/events?token=' + access).status_code == 401
        client.headers['Authorization'] = 'Bearer ' + access
        assert client.get('/api/v1/sync/events', headers={'Last-Event-ID': 'invalid'}).status_code == 422
        preflight = client.options('/api/v1/sync/events', headers={'Origin': settings.frontend_url,
            'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Headers': 'authorization,last-event-id,x-myhub-device'})
        assert preflight.status_code == 200
        claims['exp'] = math.ceil(time.time()) + 1
        client.headers['Authorization'] = 'Bearer ' + jwt.encode(claims, settings.jwt_secret_key, algorithm='HS256')
        response = client.get('/api/v1/sync/events')
        assert response.status_code == 200 and response.headers['content-type'].startswith('text/event-stream')
        assert response.headers['x-accel-buffering'] == 'no' and 'no-transform' in response.headers['cache-control']
        assert 'event: auth_expired' in response.text and access not in response.text
        assert not app.state.sync.clients
