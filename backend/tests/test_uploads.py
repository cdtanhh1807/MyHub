"""Kiểm tra resume thật qua HTTP giả lập Google, scope và giới hạn request nhỏ."""
import hashlib
import httpx
import pytest
from app.core.errors import AppError
from app.dtos.contracts import UploadRequest, UploadChunkRequest
from app.repositories.drive import DriveRepository
from app.services.uploads import UploadService, CHUNK_SIZE
from app.services.files import bytes_stream


async def test_large_upload_resume_after_restart_and_lost_response(container, settings):
    """File 104 MiB đi thành 13 request; mất phản hồi/restart không gửi trùng byte."""
    total = 13 * CHUNK_SIZE
    remote = {'offset': 0, 'digest': hashlib.sha256(), 'sizes': [], 'lost': False}
    metadata = {'id': 'large', 'name': 'large.bin', 'mimeType': 'application/octet-stream', 'size': str(total), 'parents': ['sub']}

    async def handler(request):
        """Google giả giữ offset ngay cả khi mất phản hồi sau lần nhận dữ liệu thứ hai."""
        if request.method == 'POST':
            return httpx.Response(200, headers={'Location': 'https://www.googleapis.com/upload/drive/v3/files?upload_id=secret'})
        content = await request.aread()
        if content:
            assert request.headers['content-range'].startswith(f'bytes {remote["offset"]}-')
            remote['offset'] += len(content)
            remote['sizes'].append(len(content))
            remote['digest'].update(content)
            if len(remote['sizes']) == 2 and not remote['lost']:
                remote['lost'] = True
                raise httpx.ReadError('Lost response', request=request)
        if remote['offset'] == total:
            return httpx.Response(200, json=metadata)
        return httpx.Response(308, headers={'Range': f'bytes=0-{remote["offset"] - 1}'} if remote['offset'] else {})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        repo = DriveRepository(settings, container.mongo, http)
        repo._token, repo._expires = 'test-token', 9999999999
        service = UploadService(settings, container.mongo, repo, container.scope)
        dto = UploadRequest(workspace_id='ws', file_id='sub', name='large.bin', size=total)
        state = (await service.begin(dto, 'owner')).data
        key = state['upload_id']
        assert 'secret' not in str(state)
        record = await container.mongo.get('upload_sessions', key)
        assert 'www.googleapis.com' not in str(record)
        chunk = b'x' * CHUNK_SIZE
        while not state['complete']:
            request = UploadChunkRequest(workspace_id='ws', upload_id=key, offset=state['offset'], size=len(chunk))
            try:
                state = (await service.chunk(request, 'owner', bytes_stream(chunk))).data
            except httpx.ReadError:
                service = UploadService(settings, container.mongo, repo, container.scope)
                state = (await service.status('ws', key, 'owner')).data
        assert state['offset'] == total and state['file']['id'] == 'large'
        assert remote['sizes'] == [CHUNK_SIZE] * 13
        expected = hashlib.sha256()
        for _ in range(13):
            expected.update(chunk)
        assert remote['digest'].digest() == expected.digest()
        assert (await service.status('ws', key, 'owner')).data['complete']


async def test_upload_ownership_scope_length_alignment_cancel(container, monkeypatch):
    """Chặn IDOR/đổi thư mục, offset sai, quá size và bỏ phiên khi hủy."""
    async def begin(*args):
        """URL giả hợp lệ chỉ phục vụ tạo session."""
        return 'https://www.googleapis.com/upload/drive/v3/files?upload_id=test'

    async def fail(*args):
        """Request sai phải bị từ chối trước khi tới Drive."""
        pytest.fail('Invalid upload reached Drive')

    monkeypatch.setattr(container.drive, 'begin_upload', begin, raising=False)
    monkeypatch.setattr(container.drive, 'upload_part', fail, raising=False)
    service = container.uploads
    dto = UploadRequest(workspace_id='ws', file_id='sub', name='test.bin', size=CHUNK_SIZE + 1)
    key = (await service.begin(dto, 'owner')).data['upload_id']
    for workspace, user in [('ws2', 'owner'), ('ws', 'other')]:
        with pytest.raises(AppError, match='upload_not_found'):
            await service.status(workspace, key, user)
    with pytest.raises(AppError, match='outside_workspace'):
        await service.begin(dto.model_copy(update={'file_id': 'ws2'}), 'owner')
    for offset, size, content, code in [(1, 1, b'x', 'upload_offset_mismatch'), (0, 1, b'x', 'upload_alignment'),
            (0, CHUNK_SIZE, b'x', 'upload_size_mismatch'), (0, CHUNK_SIZE, b'x' * (CHUNK_SIZE + 1), 'upload_size_mismatch')]:
        with pytest.raises(AppError, match=code):
            await service.chunk(UploadChunkRequest(workspace_id='ws', upload_id=key, offset=offset, size=size), 'owner', bytes_stream(content))
    container.drive.files['sub']['parents'] = ['ws2']
    with pytest.raises(AppError, match='outside_workspace'):
        await service.status('ws', key, 'owner')
    container.drive.files['sub']['parents'] = ['ws']
    await service.cancel('ws', key, 'owner')
    with pytest.raises(AppError, match='upload_not_found'):
        await service.status('ws', key, 'owner')


async def test_google_upload_url_range_expiry_and_empty_file(container, settings):
    """Chặn URL/Range sai, phiên hết hạn; file rỗng gửi PUT không Content-Range."""
    async def handler(request):
        """Response có thể thay theo query, không dùng mạng thật."""
        mode = request.url.params['mode']
        if mode == 'empty':
            assert request.headers['content-length'] == '0' and 'content-range' not in request.headers
            return httpx.Response(200, json={'id': 'empty'})
        if mode == 'expired':
            return httpx.Response(404)
        return httpx.Response(308, headers={'Range': 'bytes=4-8'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        repo = DriveRepository(settings, container.mongo, http)
        repo._token, repo._expires = 'test-token', 9999999999
        for bad in ['https://evil.com/upload', 'https://www.googleapis.com.evil.com/upload/drive/v3/files', 'http://www.googleapis.com/upload/drive/v3/files']:
            with pytest.raises(AppError, match='invalid_upload_session'):
                await repo.upload_part(bad, 3)
        with pytest.raises(AppError, match='upload_expired'):
            await repo.upload_part('https://www.googleapis.com/upload/drive/v3/files?mode=expired', 3)
        with pytest.raises(AppError, match='invalid_upload_response'):
            await repo.upload_part('https://www.googleapis.com/upload/drive/v3/files?mode=range', 10)
        assert (await repo.upload_part('https://www.googleapis.com/upload/drive/v3/files?mode=empty', 0, 0))[1]['id'] == 'empty'


def test_http_upload_auth_chunk_limit_and_completed_replay(container, settings, monkeypatch):
    """Kiểm thử HTTP: DTO/Content-Length, Bearer, replay hoàn tất và giới hạn 8 MiB."""
    import asyncio
    from fastapi.testclient import TestClient
    from app.main import create_app

    async def begin(*args):
        """Session URI giả không bao giờ được trả ra HTTP response."""
        return 'https://www.googleapis.com/upload/drive/v3/files?upload_id=secret'

    async def part(location, size, offset=None, content=b'', mime=''):
        """File nhỏ hoàn tất trong một phần, không tạo thêm khi browser replay."""
        assert content == b'hello'
        return size, {'id': 'uploaded', 'name': 'test.txt', 'size': str(size), 'mimeType': mime, 'parents': ['sub']}

    monkeypatch.setattr(container.drive, 'begin_upload', begin, raising=False)
    monkeypatch.setattr(container.drive, 'upload_part', part, raising=False)
    user = {'id': 'google:owner', 'name': 'Owner', 'provider': 'google', 'identity': 'owner'}
    asyncio.run(container.mongo.put('users', user['id'], user))
    token = asyncio.run(container.auth.create_session(user)).data['access_token']
    with TestClient(create_app(settings, container)) as client:
        path = '/api/v1/workspaces/ws/uploads'
        body = {'parent_id': 'sub', 'name': 'test.txt', 'size': 5, 'mime': 'text/plain'}
        assert client.post(path, json=body).status_code == 401
        client.headers['Authorization'] = 'Bearer ' + token
        response = client.post(path, json=body)
        assert response.status_code == 201 and 'secret' not in response.text
        url = path + '/' + response.json()['data']['upload_id']
        assert client.put(url + '?offset=0', content=b'hello', headers={'Content-Length': str(CHUNK_SIZE + 1)}).status_code == 422
        assert client.put(url + '?offset=0', content=b'hello').json()['data']['complete']
        assert client.put(url + '?offset=0', content=b'hello').json()['data']['file']['id'] == 'uploaded'
        assert client.get(url).json()['data']['complete']
        assert client.delete(url).status_code == 200
        assert client.get(url).status_code == 404
