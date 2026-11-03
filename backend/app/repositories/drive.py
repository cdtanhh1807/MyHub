"""Drive REST repository: CRUD, phân trang và truyền byte theo luồng."""
import asyncio
import time
from collections.abc import AsyncIterator
import httpx
from cryptography.fernet import Fernet, InvalidToken
from app.core.errors import AppError
from app.models.records import StreamRecord, ManagedStream
from app.utils.files import drive_id

FIELDS = 'id,name,mimeType,size,createdTime,modifiedTime,version,parents,trashed,webViewLink,appProperties,permissions(id,type,role,emailAddress,displayName,permissionDetails)'
BASE = 'https://www.googleapis.com/drive/v3'
UPLOAD = 'https://www.googleapis.com/upload/drive/v3/files'


class DriveRepository:
    """Dùng một token Drive mã hóa chung, độc lập nhà cung cấp đăng nhập."""
    def __init__(self, settings, mongo, client):
        """Nhận dependency → chuẩn bị cache access token ngắn hạn trong RAM."""
        self.settings, self.mongo, self.client = settings, mongo, client
        self.cipher = Fernet(settings.encryption_key.encode())
        self._token, self._expires, self._lock = '', 0, asyncio.Lock()

    async def access_token(self):
        """Giải mã refresh token → đổi access token; khóa để tránh refresh đồng thời."""
        async with self._lock:
            if self._token and self._expires > time.time() + 60:
                return self._token
            record = await self.mongo.get('drive_credentials', 'owner')
            if not record:
                raise AppError('drive_not_connected', 409)
            try:
                refresh = self.cipher.decrypt(record['encrypted_token'].encode()).decode()
            except InvalidToken:
                raise AppError('drive_key_changed', 409) from None
            response = await self.client.post('https://oauth2.googleapis.com/token', data={
                'client_id': self.settings.google_client_id, 'client_secret': self.settings.google_client_secret,
                'refresh_token': refresh, 'grant_type': 'refresh_token',
            })
            if response.status_code != 200:
                raise AppError('drive_reconnect_required', 409)
            data = response.json()
            self._token, self._expires = data['access_token'], time.time() + data.get('expires_in', 3600)
            return self._token

    async def request(self, method, path, **kwargs):
        """Gửi request metadata đến Drive; chuyển lỗi upstream thành mã an toàn."""
        headers = kwargs.pop('headers', {})
        response = await self.client.request(method, f'{BASE}/{path}', headers={**headers, 'Authorization': f'Bearer {await self.access_token()}'}, **kwargs)
        self.check(response)
        return response

    @staticmethod
    def check(response):
        """Không đưa response Google có thông tin nội bộ ra phía trình duyệt."""
        if response.status_code >= 400:
            status = response.status_code if response.status_code in (403, 404, 409, 412, 416, 429) else 502
            raise AppError('conflict' if status == 412 else f'drive_error_{status}', status)

    async def get(self, file_id):
        """Lấy metadata đầy đủ, ID luôn validate trước khi tạo URL."""
        response = await self.request('GET', f'files/{drive_id(file_id)}', params={'fields': FIELDS})
        return response.json()

    async def list_query(self, query):
        """Theo toàn bộ nextPageToken; không cắt mất file sau trang đầu."""
        result, page = [], None
        while True:
            params = {'q': query, 'pageSize': 1000, 'fields': f'nextPageToken,files({FIELDS})'}
            if page:
                params['pageToken'] = page
            data = (await self.request('GET', 'files', params=params)).json()
            result.extend(data.get('files', []))
            page = data.get('nextPageToken')
            if not page:
                return result

    async def children(self, parent_id, trashed=False):
        """Liệt kê con trực tiếp; escape ID được thực hiện bằng whitelist ký tự."""
        return await self.list_query(f"'{drive_id(parent_id)}' in parents and trashed = {'true' if trashed else 'false'}")

    async def trash_candidates(self):
        """Lấy metadata thùng rác; Service kiểm tra lại phạm vi từng mục."""
        return await self.list_query('trashed = true')

    async def create_folder(self, name, parent, system=False):
        """Tạo folder trên Drive, đánh dấu folder hệ thống để ẩn khỏi Workspace."""
        metadata = {'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [drive_id(parent)]}
        if system:
            metadata['appProperties'] = {'myhubSystem': 'true'}
        return (await self.request('POST', 'files', json=metadata, params={'fields': FIELDS})).json()

    async def update(self, file_id, metadata, **params):
        """Cập nhật metadata (đổi tên/trash/di chuyển), trả metadata mới."""
        return (await self.request('PATCH', f'files/{drive_id(file_id)}', json=metadata, params={'fields': FIELDS, **params})).json()

    async def delete_temporary(self, file_id):
        """Chỉ Service chuyển đổi gọi xóa vĩnh viễn bản sao hệ thống do nó tạo."""
        await self.request('DELETE', f'files/{drive_id(file_id)}')

    async def copy(self, file_id, parent, name):
        """Sao chép file ngay trên Drive, không tải nội dung về máy backend."""
        return (await self.request('POST', f'files/{drive_id(file_id)}/copy', json={'name': name, 'parents': [drive_id(parent)]}, params={'fields': FIELDS})).json()

    async def upload(self, parent, name, mime, size, content: AsyncIterator[bytes], file_id=None, google_mime=None):
        """Mở resumable session → truyền raw stream; không spool upload vào đĩa."""
        metadata = {} if file_id else {'name': name, 'parents': [drive_id(parent)]}
        if google_mime:
            metadata['mimeType'] = google_mime
        path = UPLOAD + (f'/{drive_id(file_id)}' if file_id else '')
        init = await self.client.request('PATCH' if file_id else 'POST', path, params={'uploadType': 'resumable', 'fields': FIELDS},
            headers={'Authorization': f'Bearer {await self.access_token()}', 'X-Upload-Content-Type': mime, 'X-Upload-Content-Length': str(size)}, json=metadata)
        self.check(init)
        location = init.headers.get('location', '')
        if not location.startswith('https://www.googleapis.com/'):
            raise AppError('invalid_upload_session', 502)
        result = await self.client.put(location, headers={'Content-Type': mime, 'Content-Length': str(size)}, content=content)
        self.check(result)
        return result.json()

    async def stream(self, file_id, range_header=None, export_mime=None, revision_id=None):
        """Mở response trước khi trả header; iterator đóng upstream cả khi hủy tải."""
        path = f'files/{drive_id(file_id)}'
        params = {'alt': 'media'}
        if revision_id:
            path += f'/revisions/{drive_id(revision_id)}'
        if export_mime:
            path += '/export'
            params = {'mimeType': export_mime}
        headers = {'Authorization': f'Bearer {await self.access_token()}', 'Accept-Encoding': 'identity'}
        if range_header:
            headers['Range'] = range_header
        response = await self.client.send(self.client.build_request('GET', f'{BASE}/{path}', params=params, headers=headers), stream=True)
        try:
            self.check(response)
        except BaseException:
            await response.aclose()
            raise

        async def chunks():
            """Đọc chunk giới hạn → giải phóng socket khi stream kết thúc/ngắt."""
            try:
                async for chunk in response.aiter_bytes(256 * 1024):
                    yield chunk
            finally:
                await response.aclose()

        forwarded = {key: value for key, value in response.headers.items() if key.lower() in ('content-type', 'content-length', 'content-range', 'accept-ranges')}
        return StreamRecord(ManagedStream(chunks(), response.aclose), forwarded, response.status_code)

    async def permissions(self, file_id, method='GET', permission_id=None, body=None, notify=False):
        """CRUD quyền Drive, phân trang danh sách và không tự gửi thông báo."""
        path = f'files/{drive_id(file_id)}/permissions'
        if permission_id:
            path += f'/{drive_id(permission_id)}'
        if method == 'GET':
            permissions, page = [], None
            while True:
                params = {'fields': 'nextPageToken,permissions(id,type,role,emailAddress,displayName,permissionDetails)', 'pageSize': 100}
                if page:
                    params['pageToken'] = page
                data = (await self.request(method, path, params=params)).json()
                permissions.extend(data.get('permissions', []))
                page = data.get('nextPageToken')
                if not page:
                    return permissions
        params = {'sendNotificationEmail': str(notify).lower()} if method == 'POST' else {}
        result = await self.request(method, path, json=body, params=params)
        return result.json() if result.content else None

    async def revisions(self, file_id):
        """Lấy mọi trang revision hiện được Google giữ lại, không cam kết giữ lâu dài."""
        revisions, page = [], None
        while True:
            params = {'fields': 'nextPageToken,revisions(id,modifiedTime,size,keepForever)', 'pageSize': 1000}
            if page:
                params['pageToken'] = page
            data = (await self.request('GET', f'files/{drive_id(file_id)}/revisions', params=params)).json()
            revisions.extend(data.get('revisions', []))
            page = data.get('nextPageToken')
            if not page:
                return revisions
