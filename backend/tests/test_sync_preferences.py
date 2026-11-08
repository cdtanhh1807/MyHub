"""Hồi quy thùng rác toàn root, cài đặt nhiều thiết bị và tín hiệu đồng bộ có xác thực."""
import asyncio
from fastapi.testclient import TestClient
from app.main import create_app
from app.dtos.contracts import SettingsRequest, OrderRequest


async def test_device_settings_and_orders_are_isolated(container):
    """Hai máy cùng tài khoản giữ theme, sort và thứ tự riêng; tài khoản khác không đọc được."""
    await container.workspaces.settings_save('owner', SettingsRequest(theme='dark', workspace_sort='manual'), 'laptop')
    await container.workspaces.settings_save('owner', SettingsRequest(theme='light', language='en', workspace_sort='manual'), 'phone')
    await container.workspaces.order('owner', OrderRequest(ids=['ws2', 'ws']), 'laptop')
    await container.workspaces.order('owner', OrderRequest(ids=['ws', 'ws2']), 'phone')
    assert (await container.workspaces.settings_get('owner', 'laptop')).data['theme'] == 'dark'
    assert (await container.workspaces.settings_get('owner', 'phone')).data['language'] == 'en'
    assert (await container.workspaces.settings_get('other-user', 'laptop')).data['theme'] == 'system'
    assert [item.id for item in (await container.workspaces.listing('owner', 'laptop')).files] == ['ws2', 'ws']
    assert [item.id for item in (await container.workspaces.listing('owner', 'phone')).files] == ['ws', 'ws2']
    # Client cũ không có device vẫn dùng được nhưng không làm thay đổi vùng browser mới.
    await container.workspaces.settings_save('owner', SettingsRequest(theme='light'))
    assert (await container.workspaces.settings_get('owner', 'laptop')).data['theme'] == 'dark'


async def test_global_trash_excludes_system_external_cycles_and_shortcuts(container):
    """Toàn root bao gồm mục lồng sâu; không lộ backup, shortcut hoặc mục ngoài phạm vi."""
    drive = container.drive
    for key in ('text', 'other', 'system_file', 'external_file'):
        drive.files[key]['trashed'] = True
    drive.files['cycle'] = {**drive.files['text'], 'id': 'cycle', 'parents': ['cycle']}
    drive.files['shortcut'] = {**drive.files['text'], 'id': 'shortcut', 'mimeType': 'application/vnd.google-apps.shortcut'}
    drive.files['direct'] = {**drive.files['text'], 'id': 'direct', 'parents': ['root']}
    drive.files['nested']['trashed'] = True
    result = await container.files.trash_list()
    assert {item.id for item in result.files} == {'text', 'other', 'nested'}
    assert {item.workspace_name for item in result.files} == {'Workspace', 'Other'}
    assert {item.id for item in (await container.files.trash_list('ws2')).files} == {'other'}


def test_sync_requires_auth_and_covers_mutations(settings, container):
    """Mọi nhóm thay đổi đều làm mới revision; cấp cookie/đọc API không gây vòng lặp."""
    user = {'id': 'owner', 'name': 'Owner', 'identity': 'owner@example.com', 'provider': 'google'}
    asyncio.run(container.mongo.put('users', 'owner', user))
    token = asyncio.run(container.auth.create_session(user)).data['access_token']
    app = create_app(settings, container)
    with TestClient(app) as client:
        assert client.get('/api/v1/sync').status_code == 401
        client.headers['Authorization'] = 'Bearer ' + token
        # Header thiết bị được validate và phân vùng tại biên API, không chỉ ở Service.
        assert client.put('/api/v1/settings', headers={'X-MyHub-Device': '../bad'}, json={}).status_code == 422
        assert client.put('/api/v1/settings', headers={'X-MyHub-Device': 'A'}, json={'theme': 'dark'}).status_code == 200
        assert client.get('/api/v1/settings', headers={'X-MyHub-Device': 'B'}).json()['data']['theme'] == 'system'
        assert client.get('/api/v1/settings', headers={'X-MyHub-Device': 'A'}).json()['data']['theme'] == 'dark'

        def revision():
            """Chỉ đọc token công khai, không dùng dịch vụ Drive/Mongo thật."""
            return client.get('/api/v1/sync').json()['data']['revision']

        previous = revision()
        assert client.post('/api/v1/workspaces/ws/files/text/access').status_code == 200
        assert revision() == previous
        mutations = [
            ('post', '/workspaces', {'name': 'Created'}),
            ('patch', '/workspaces/ws', {'name': 'Renamed'}),
            ('post', '/workspaces/ws/folders', {'parent_id': 'ws', 'name': 'New folder'}),
            ('patch', '/workspaces/ws/files/text', {'name': 'changed.py'}),
            ('put', '/workspaces/ws/files/text/text', {'content': 'updated', 'version': '2'}),
            ('post', '/workspaces/ws/files/text/permissions', {'type': 'anyone', 'role': 'reader'}),
            ('post', '/workspaces/ws/files/text/transfer', {'mode': 'copy', 'target_workspace_id': 'ws2', 'target_folder_id': 'ws2'}),
            ('delete', '/workspaces/ws/files/text', None),
            ('post', '/workspaces/ws/files/text/restore', {}),
        ]
        for method, path, body in mutations:
            response = client.request(method, '/api/v1' + path, json=body)
            assert response.status_code < 300, (path, response.text)
            current = revision()
            assert current != previous, path
            previous = current
        assert client.get('/api/v1/sync/events', headers={'Authorization': ''}).status_code == 401
    # Restart giữ log/cursor trong Mongo và thêm reset mới, không làm mất lịch sử thiết bị offline.
    with TestClient(create_app(settings, container)) as restarted:
        restarted.headers['Authorization'] = 'Bearer ' + token
        assert restarted.get('/api/v1/sync').json()['data']['revision'] != previous
        assert container.mongo.documents[('sync_log', 'root')]['events'][-1]['kind'] == 'reset'
