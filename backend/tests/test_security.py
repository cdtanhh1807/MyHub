"""Kiểm thử truy cập sai phạm vi, OAuth và vòng đời token thay vì chỉ happy path."""
from datetime import datetime, timedelta, timezone
import asyncio
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.errors import AppError
from app.dtos.contracts import FileRequest, SaveRequest, TransferRequest, DeleteWorkspaceRequest, NameRequest, PermissionRequest
from app.services.auth import digest


@pytest.mark.parametrize('workspace,file_id', [('ws', 'other'), ('ws', 'external_file'), ('ws', 'system_file'), ('system', 'system_file'), ('outside', 'external_file'), ('ws', 'root')])
async def test_boundaries(container, workspace, file_id):
    """File ở Workspace khác, ngoài root hoặc system đều không được đọc."""
    with pytest.raises(AppError) as error:
        await container.files.text(FileRequest(workspace_id=workspace, file_id=file_id))
    assert error.value.status == 403
    assert not container.drive.calls


async def test_parent_cycle_and_shortcut(container):
    """Metadata có cycle/shortcut không thể bypass cây Workspace."""
    container.drive.files['text']['parents'] = ['text']
    with pytest.raises(AppError):
        await container.scope.file('ws', 'text')
    container.drive.files['text'].update(parents=['sub'], mimeType='application/vnd.google-apps.shortcut')
    with pytest.raises(AppError, match='shortcut_not_supported'):
        await container.scope.file('ws', 'text')


async def test_source_of_truth_and_unique_names(container):
    """Folder tạo ngoài app vẫn thành Workspace; folder hệ thống bị ẩn."""
    result = await container.workspaces.listing('user')
    assert {f.id for f in result.files} == {'ws', 'ws2'}
    with pytest.raises(AppError, match='duplicate_workspace'):
        await container.workspaces.create(NameRequest(name='workspace'))


async def test_editor_conflict_and_same_id(container):
    """Stale save không được ghi; save hợp lệ giữ ID và tạo revision/version mới."""
    with pytest.raises(AppError, match='conflict'):
        await container.files.save(SaveRequest(workspace_id='ws', file_id='text', content='new', version='old'))
    assert not container.drive.calls
    result = await container.files.save(SaveRequest(workspace_id='ws', file_id='text', content='new', version='1'))
    assert result.id == 'text' and result.version == '2'
    assert container.drive.contents['text'] == b'new'


async def test_conflict_copy_preserves_original(container):
    """Save-copy không làm thay đổi nội dung hoặc metadata file nguồn."""
    result = await container.files.save(SaveRequest(workspace_id='ws', file_id='text', content='my copy', version='old', strategy='copy'))
    assert result.id != 'text'
    assert container.drive.contents['text'] == b'hello'


async def test_transfer_boundaries_and_cycle(container):
    """Đích ngoài root/cây con nguồn bị từ chối trước mutation."""
    for values in [dict(file_id='sub', target_workspace_id='ws', target_folder_id='nested'), dict(file_id='text', target_workspace_id='outside', target_folder_id='outside')]:
        with pytest.raises(AppError):
            await container.files.transfer(TransferRequest(workspace_id='ws', mode='move', **values))
    assert not container.drive.calls
    result = await container.files.transfer(TransferRequest(workspace_id='ws', file_id='text', target_workspace_id='ws2', target_folder_id='ws2', mode='move'))
    assert result.parents == ['ws2']


async def test_two_step_workspace_delete(container):
    """Snapshot/tên phải khớp, nếu đổi nội dung giữa hai bước thì không được trash."""
    impact = await container.workspaces.impact('ws', 'owner')
    assert impact.data['count'] == 3
    token = impact.data['confirmation_token']
    with pytest.raises(AppError, match='confirmation_changed'):
        await container.workspaces.delete(DeleteWorkspaceRequest(workspace_id='ws', confirmation_name='wrong', confirmation_token=token), 'owner')
    container.drive.files['text']['version'] = '2'
    with pytest.raises(AppError, match='confirmation_changed'):
        await container.workspaces.delete(DeleteWorkspaceRequest(workspace_id='ws', confirmation_name='Workspace', confirmation_token=token), 'owner')
    assert not container.drive.files['ws']['trashed']
    impact = await container.workspaces.impact('ws', 'owner')
    await container.workspaces.delete(DeleteWorkspaceRequest(workspace_id='ws', confirmation_name='Workspace', confirmation_token=impact.data['confirmation_token']), 'owner')
    assert container.drive.files['ws']['trashed']


@pytest.mark.parametrize('provider,profile,allowed', [
    ('google', {'email': 'cdtanhh@gmail.com', 'email_verified': True}, True),
    ('google', {'email': 'cdtanhh@gmail.com', 'email_verified': False}, False),
    ('google', {'email': 'intruder@gmail.com', 'email_verified': True}, False),
    ('github', {'login': 'cdtanhh1807', 'id': 98765}, True),
    ('github', {'login': 'intruder', 'id': 98765}, False),
])
def test_exact_whitelist(container, provider, profile, allowed):
    """Google email đã xác minh và GitHub username là hai điều kiện riêng biệt."""
    assert container.auth.allowed(provider, profile) is allowed


async def test_state_binding_and_one_time_use(container):
    """Sai browser/provider bị chặn và state đã consume không thể phát lại."""
    result = await container.auth.begin('google')
    state = result.data['url'].split('=')[1]
    with pytest.raises(AppError, match='invalid_oauth_state'):
        await container.auth.callback('github', state, result.data['browser'], 'code')
    with pytest.raises(AppError, match='invalid_oauth_state'):
        await container.auth.callback('google', state, result.data['browser'], 'code')


async def test_drive_token_encrypted_and_login_independent(container, settings):
    """Phiên GitHub có thể cấp Drive chủ Google; chỉ ciphertext được lưu vào Mongo."""
    user = {'id': 'github:cdtanhh1807'}
    result = await container.auth.begin('drive', user)
    state = result.data['url'].split('=')[1]
    await container.auth.callback('drive', state, result.data['browser'], 'code', user)
    record = await container.mongo.get('drive_credentials', 'owner')
    assert record['email'] == 'cdtanhh@gmail.com'
    assert 'fake-drive-refresh' not in str(record)
    assert container.drive._token == ''


async def test_drive_connection_checks_root(container):
    """Không báo connected khi root bị xóa hoặc ID trỏ nhầm file thường."""
    assert (await container.auth.connection()).data['connected']
    container.drive.files['root']['trashed'] = True
    result = await container.auth.connection()
    assert not result.data['connected'] and result.data['reason'] == 'invalid_drive_root'


async def test_drive_missing_scope_not_persisted(container, monkeypatch):
    """Người dùng bỏ quyền Drive trong consent thì không lưu credential không đủ scope."""
    async def limited_token(*args):
        """Provider trả token hợp lệ cho profile nhưng không có quyền Drive."""
        return {'refresh_token': 'fake-limited', 'scope': 'openid email profile'}, {'email': 'cdtanhh@gmail.com', 'email_verified': True}

    monkeypatch.setattr(container.auth.oauth, 'exchange', limited_token)
    user = {'id': 'github:cdtanhh1807'}
    started = await container.auth.begin('drive', user)
    with pytest.raises(AppError, match='drive_scope_missing'):
        await container.auth.callback('drive', started.data['url'].split('=')[1], started.data['browser'], 'code', user)
    assert await container.mongo.get('drive_credentials', 'owner') is None


async def test_refresh_rotation_replay_and_logout(container):
    """Hai refresh cùng token chỉ một thành công; logout thu hồi cả access JWT."""
    user = {'id': 'google:owner', 'name': 'Owner', 'identity': 'owner', 'provider': 'google'}
    await container.mongo.put('users', user['id'], user)
    session = (await container.auth.create_session(user)).data
    outcomes = await asyncio.gather(container.auth.refresh(session['refresh_token']), container.auth.refresh(session['refresh_token']), return_exceptions=True)
    assert sum(isinstance(value, AppError) for value in outcomes) == 1
    fresh = next(value.data for value in outcomes if not isinstance(value, Exception))
    await container.auth.logout(fresh['refresh_token'])
    with pytest.raises(AppError, match='unauthorized'):
        await container.auth.authenticate(fresh['access_token'])


async def test_expired_session_rejected_before_ttl_sweep(container):
    """Không tin TTL đã xóa đúng giây; session hết hạn bị kiểm tra trực tiếp."""
    await container.mongo.put('refresh_sessions', 'expired', {'user_id': 'owner', 'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)})
    with pytest.raises(AppError, match='unauthorized'):
        await container.auth.user_for_session('expired')


async def test_sharing_roles_link_notify_and_scope(container):
    """Mời email, đổi role, restricted và owner protection không được bypass scope."""
    request = FileRequest(workspace_id='ws', file_id='text')
    invited = await container.sharing.create(request, PermissionRequest(email='friend@example.com', role='commenter', notify=True))
    assert container.drive.calls[-1] == ('permissions', 'text', 'POST', True)
    await container.sharing.mutate(request, invited.data['id'], PermissionRequest(role='writer'))
    assert (await container.sharing.listing(request)).data['permissions'][0]['role'] == 'writer'
    link = await container.sharing.create(request, PermissionRequest(type='anyone', role='reader'))
    await container.sharing.mutate(request, link.data['id'])
    assert all(p['type'] != 'anyone' for p in (await container.sharing.listing(request)).data['permissions'])
    container.drive.files['text']['permissions'].append({'id': 'owner', 'type': 'user', 'role': 'owner'})
    with pytest.raises(AppError, match='permission_not_editable'):
        await container.sharing.mutate(request, 'owner')
    before = len(container.drive.calls)
    with pytest.raises(AppError, match='outside_workspace'):
        await container.sharing.create(FileRequest(workspace_id='ws', file_id='other'), PermissionRequest(email='friend@example.com'))
    assert len(container.drive.calls) == before


def test_http_auth_origin_range_and_media_scope(container, settings):
    """Kiểm tra cả HTTP layer: cookie không đổi được file, Range trả 206, refresh chặn CSRF."""
    app = create_app(settings, container)
    with TestClient(app) as client:
        import asyncio
        user = {'id': 'google:owner', 'name': 'Owner', 'identity': 'owner', 'provider': 'google'}
        asyncio.run(container.mongo.put('users', user['id'], user))
        session = asyncio.run(container.auth.create_session(user)).data
        headers = {'Authorization': 'Bearer ' + session['access_token']}
        assert client.get('/api/v1/workspaces').status_code == 401
        assert client.post('/api/v1/auth/refresh', headers={'Origin': 'https://evil.example'}).status_code == 403
        response = client.get('/api/v1/workspaces/ws/files/text/content', headers={**headers, 'Range': 'bytes=1-2'})
        assert response.status_code == 206 and response.content == b'el'
        assert response.headers['content-range'] == 'bytes 1-2/5'
        assert client.post('/api/v1/workspaces/ws/files/text/access', headers=headers).status_code == 200
        assert client.get('/api/v1/workspaces/ws/files/text/content').status_code == 200
        assert client.get('/api/v1/workspaces/ws/files/other/content').status_code == 401
        assert client.patch('/api/v1/workspaces/ws/files/text', json={'name': 'evil'}).status_code == 401
        assert client.get('/api/v1/workspaces/ws2/files/other/content', headers=headers).status_code == 200
        assert client.get('/api/v1/workspaces/ws/files/other/content', headers=headers).status_code == 403
        assert client.patch('/api/v1/workspaces/ws/files/text', json={'name': '../oops'}, headers=headers).status_code == 422
