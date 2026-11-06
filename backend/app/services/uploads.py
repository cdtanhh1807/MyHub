"""Upload nhiều request nhỏ qua Cloudflare, phiên và URL Drive giữ kín ở server."""
import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from app.core.errors import AppError
from app.dtos.contracts import FileDTO, ResultDTO

CHUNK_SIZE = 8 * 1024 * 1024
ALIGNMENT = 256 * 1024


class UploadService:
    """Một worker tuần tự hóa thao tác phiên; Mongo giữ offset qua lần restart/deploy."""
    def __init__(self, settings, mongo, drive, scope):
        """Dùng khóa mã hóa hiện có và khóa trong process, không giữ dữ liệu file trên đĩa."""
        self.mongo, self.drive, self.scope = mongo, drive, scope
        self.cipher = Fernet(settings.encryption_key.encode())
        self.lock = asyncio.Lock()

    @staticmethod
    def response(record):
        """Service tạo DTO công khai, không lộ URL upload hoặc credential của Google."""
        return ResultDTO(data={'upload_id': record['_id'], 'offset': record['offset'], 'size': record['size'],
            'chunk_size': CHUNK_SIZE, 'complete': record.get('file') is not None, 'file': record.get('file')})

    async def begin(self, request, user_id):
        """Xác thực đích trước khi mở phiên; TTL ngắn hơn thời hạn một tuần của Drive."""
        await self.scope.folder(request.workspace_id, request.file_id)
        location = await self.drive.begin_upload(request.file_id, request.name, request.mime, request.size)
        key = secrets.token_urlsafe(32)
        record = {'_id': key, 'user_id': user_id, 'workspace_id': request.workspace_id, 'parent_id': request.file_id,
            'size': request.size, 'mime': request.mime, 'offset': 0, 'file': None,
            'location': self.cipher.encrypt(location.encode()).decode(),
            'expires_at': datetime.now(timezone.utc) + timedelta(days=6)}
        await self.mongo.put('upload_sessions', key, record)
        return self.response(record)

    async def record(self, workspace_id, upload_id, user_id):
        """ID phiên phải thuộc đúng người/Workspace và thư mục vẫn trong scope hiện tại."""
        record = await self.mongo.get('upload_sessions', upload_id)
        if not record or record['user_id'] != user_id or record['workspace_id'] != workspace_id:
            raise AppError('upload_not_found', 404)
        if record['expires_at'] <= datetime.now(timezone.utc):
            raise AppError('upload_expired', 410)
        await self.scope.folder(workspace_id, record['parent_id'])
        return record

    async def persist(self, record, offset, file):
        """Lưu offset Google xác nhận; chỉ đánh dấu hoàn tất khi metadata hợp lệ."""
        record['offset'] = offset
        if file is not None:
            record['file'] = FileDTO(**file).model_dump()
        await self.mongo.put('upload_sessions', record['_id'], record)
        return self.response(record)

    async def status(self, workspace_id, upload_id, user_id):
        """Hỏi Drive sau lỗi mạng để không đoán phần dữ liệu đã nhận."""
        async with self.lock:
            record = await self.record(workspace_id, upload_id, user_id)
            if record.get('file'):
                return self.response(record)
            offset, file = await self.drive.upload_part(self.cipher.decrypt(record['location']).decode(), record['size'])
            return await self.persist(record, offset, file)

    async def chunk(self, request, user_id, content):
        """Giới hạn buffer 8 MiB, kiểm tra offset/byte trước khi chuyển phần đó lên Drive."""
        async with self.lock:
            record = await self.record(request.workspace_id, request.upload_id, user_id)
            if record.get('file'):
                return self.response(record)
            end = request.offset + request.size
            if request.offset != record['offset']:
                raise AppError('upload_offset_mismatch', 409)
            if end > record['size'] or (request.size == 0 and record['size'] != 0):
                raise AppError('upload_size_mismatch', 400)
            if end < record['size'] and request.size % ALIGNMENT:
                raise AppError('upload_alignment', 400)
            buffer = bytearray()
            async for part in content:
                if len(buffer) + len(part) > request.size:
                    raise AppError('upload_size_mismatch', 400)
                buffer.extend(part)
            if len(buffer) != request.size:
                raise AppError('upload_size_mismatch', 400)
            offset, file = await self.drive.upload_part(self.cipher.decrypt(record['location']).decode(),
                record['size'], request.offset, bytes(buffer), record['mime'])
            return await self.persist(record, offset, file)

    async def cancel(self, workspace_id, upload_id, user_id):
        """Thu hồi phiên trong app; phần chưa hoàn tất trên Drive tự hết hạn, không xóa file thật."""
        async with self.lock:
            await self.record(workspace_id, upload_id, user_id)
            await self.mongo.remove('upload_sessions', upload_id)
            return ResultDTO(data={'cancelled': True})
