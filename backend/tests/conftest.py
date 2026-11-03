"""Fixture dữ liệu độc lập dịch vụ thật, không tạo file hay credential người dùng."""
import copy
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from cryptography.fernet import Fernet
from app.config.settings import Settings
from app.core.errors import AppError
from app.models.records import StreamRecord
from app.services.auth import AuthService
from app.services.scope import ScopeService
from app.services.files import FileService
from app.services.workspaces import WorkspaceService
from app.services.sharing import SharingService
from app.services.preview import PreviewService
from app.services.archive import ArchiveService
from app.utils.files import FOLDER


def pytest_configure(config):
    """Đặt tmp của test vào data trong repo thay vì để lại bản sao bên ngoài dự án."""
    from pathlib import Path
    if config.option.basetemp is None:
        config.option.basetemp = str(Path(__file__).resolve().parents[2] / 'data' / 'test-tmp')


class FakeMongo:
    """Mô phỏng lưu metadata và consume nguyên tử cho kiểm thử auth."""
    def __init__(self):
        """Tạo DB riêng cho mỗi test để không dùng state toàn cục."""
        self.documents = {}

    async def get(self, collection, key):
        """Trả bản sao giống hành vi đọc document từ DB thật."""
        return copy.deepcopy(self.documents.get((collection, key)))

    async def put(self, collection, key, values):
        """Upsert mô phỏng, không giữ tham chiếu mutable của Service."""
        self.documents[(collection, key)] = {**self.documents.get((collection, key), {}), **copy.deepcopy(values), '_id': key}

    async def remove(self, collection, key):
        """Xóa idempotent để test logout/revocation."""
        self.documents.pop((collection, key), None)

    async def consume(self, collection, key):
        """Chỉ trả record chưa hết hạn và xóa trong cùng thao tác."""
        record = self.documents.pop((collection, key), None)
        return record if record and record['expires_at'] > datetime.now(timezone.utc) else None


class FakeDrive:
    """Cây Drive có cả file ngoài root, system folder và workspace khác."""
    def __init__(self):
        """Dựng cây kiểm tra IDOR và dữ liệu media nhỏ phục vụ test."""
        self.files, self.contents, self.calls = {}, {}, []
        for key, name, parent, mime in [
            ('root', 'MyHub', 'external', FOLDER), ('ws', 'Workspace', 'root', FOLDER), ('ws2', 'Other', 'root', FOLDER),
            ('system', '.myhub-system', 'root', FOLDER), ('sub', 'Sub', 'ws', FOLDER), ('nested', 'Nested', 'sub', FOLDER),
            ('text', 'hello.py', 'sub', 'text/plain'), ('other', 'secret.txt', 'ws2', 'text/plain'),
            ('outside', 'Outside', 'external', FOLDER), ('external_file', 'secret.txt', 'outside', 'text/plain'),
            ('system_file', 'backup.gz', 'system', 'application/gzip')]:
            self.files[key] = {'id': key, 'name': name, 'parents': [parent], 'mimeType': mime, 'version': '1', 'trashed': False, 'permissions': [], 'size': None if mime == FOLDER else '5'}
            if mime != FOLDER:
                self.contents[key] = b'hello'

    async def get(self, file_id):
        """Tra ID không tồn tại trả lỗi như Drive thay vì tự tạo dữ liệu."""
        if file_id not in self.files:
            raise AppError('drive_error_404', 404)
        return copy.deepcopy(self.files[file_id])

    async def access_token(self):
        """Token stub không có giá trị thực, phục vụ kiểm tra tình trạng kết nối root."""
        return 'test-drive-access'

    async def children(self, parent_id, trashed=False):
        """Con trực tiếp theo trạng thái trash, đủ để Service tự kiểm tra cây."""
        return [copy.deepcopy(f) for f in self.files.values() if parent_id in f['parents'] and f['trashed'] == trashed]

    async def update(self, file_id, metadata, **params):
        """Ghi lại mutation để test bảo đảm request bị chặn chưa chạm Drive."""
        self.calls.append(('update', file_id, metadata, params))
        self.files[file_id].update(metadata)
        if 'addParents' in params:
            self.files[file_id]['parents'] = [params['addParents']]
        self.files[file_id]['version'] = str(int(self.files[file_id]['version']) + 1)
        return await self.get(file_id)

    async def create_folder(self, name, parent, system=False):
        """Tạo folder mô phỏng để kiểm tra Workspace source of truth."""
        key = f'new{len(self.files)}'
        self.files[key] = {'id': key, 'name': name, 'parents': [parent], 'mimeType': FOLDER, 'version': '1', 'trashed': False}
        if system:
            self.files[key]['appProperties'] = {'myhubSystem': 'true'}
        return await self.get(key)

    async def stream(self, file_id, range_header=None, export_mime=None, revision_id=None):
        """Mô phỏng response 206 để kiểm tra Controller giữ status/header."""
        self.calls.append(('stream', file_id, range_header))
        content = self.contents.get(file_id, b'hello')
        headers = {'Content-Type': 'text/plain', 'Content-Length': str(len(content)), 'Accept-Ranges': 'bytes'}
        status = 200
        if range_header:
            content = content[1:3]
            headers.update({'Content-Range': 'bytes 1-2/5', 'Content-Length': '2'})
            status = 206

        async def chunks():
            """Byte chunks thay vì một response buffer từ repository thật."""
            for byte in content:
                yield bytes([byte])

        return StreamRecord(chunks(), headers, status)

    async def upload(self, parent, name, mime, size, content, file_id=None, google_mime=None):
        """Ghi nội dung test nhỏ và version mới; ID cũ giữ nguyên khi update."""
        self.calls.append(('upload', file_id, parent, google_mime))
        value = b''.join([chunk async for chunk in content])
        assert len(value) == size
        key = file_id or f'upload{len(self.files)}'
        old = self.files.get(key, {})
        self.files[key] = {**old, 'id': key, 'name': name, 'mimeType': google_mime or mime, 'parents': [parent], 'size': str(size), 'version': str(int(old.get('version', '0')) + 1), 'trashed': False}
        self.contents[key] = value
        return await self.get(key)

    async def copy(self, file_id, parent, name):
        """Không cần tải byte khi copy; fixture dùng cùng upload giả để giữ metadata."""
        from app.services.files import bytes_stream
        content = self.contents[file_id]
        return await self.upload(parent, name, self.files[file_id]['mimeType'], len(content), bytes_stream(content))

    async def trash_candidates(self):
        """Danh sách trash toàn Drive để kiểm tra Service không rò file ngoài root."""
        return [copy.deepcopy(f) for f in self.files.values() if f['trashed']]

    async def revisions(self, file_id):
        """Một revision có size để test phục hồi cùng ID."""
        return [{'id': 'rev1', 'size': '5', 'modifiedTime': '2026-01-01T00:00:00Z'}]

    async def permissions(self, file_id, method='GET', permission_id=None, body=None, notify=False):
        """Mô phỏng quyền thật để kiểm tra share service và cờ gửi thông báo."""
        self.calls.append(('permissions', file_id, method, notify))
        permissions = self.files[file_id].setdefault('permissions', [])
        if method == 'GET':
            return copy.deepcopy(permissions)
        if method == 'POST':
            permission = {'id': f'perm{len(permissions)}', **body}
            permissions.append(permission)
            return copy.deepcopy(permission)
        existing = next(p for p in permissions if p['id'] == permission_id)
        if method == 'DELETE':
            permissions.remove(existing)
            return None
        existing.update(body)
        return copy.deepcopy(existing)

    async def delete_temporary(self, file_id):
        """Chỉ ghi nhận việc xóa tạm, giúp assert file gốc không bị xóa."""
        self.calls.append(('delete_temporary', file_id))
        self.files.pop(file_id, None)


class FakeOAuth:
    """Không gọi provider thật; profile test vẫn được AuthService whitelist."""
    async def authorization_url(self, provider, redirect_uri, state, verifier):
        """URL stub để kiểm tra state/PKCE tại tầng Service."""
        return 'https://example.com/authorize?state=' + state

    async def exchange(self, provider, redirect_uri, code, verifier):
        """Trả profile chủ sở hữu và refresh Drive giả không có giá trị thực."""
        return {'refresh_token': 'fake-drive-refresh'}, {'email': 'cdtanhh@gmail.com', 'email_verified': True, 'name': 'Owner', 'login': 'cdtanhh1807'}


@pytest.fixture
def settings(tmp_path):
    """Khóa ngẫu nhiên mỗi test, không đọc backend/.env thật."""
    return Settings(_env_file=None, jwt_secret_key='test-only-' * 8, encryption_key=Fernet.generate_key().decode(),
        mongodb_uri='mongodb://localhost:27017', google_drive_root_folder_id='root', local_data_dir=tmp_path, archive_max_mb=1)


@pytest.fixture
def container(settings):
    """Ghép Service thật trên kho giả, kiểm thử cả nghiệp vụ chứ không mirror implementation."""
    mongo, drive, oauth = FakeMongo(), FakeDrive(), FakeOAuth()
    scope = ScopeService(settings, drive)
    return SimpleNamespace(mongo=mongo, drive=drive, scope=scope, auth=AuthService(settings, mongo, oauth, drive),
        files=FileService(settings, drive, scope), workspaces=WorkspaceService(settings, mongo, drive, scope),
        sharing=SharingService(drive, scope), preview=PreviewService(settings, mongo, drive, scope), archive=ArchiveService(settings, drive, scope))
