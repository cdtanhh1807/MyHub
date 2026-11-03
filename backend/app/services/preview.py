"""Office → bản Google tạm → PDF, cache có giới hạn và fallback rõ ràng."""
import asyncio
import hashlib
import logging
from pathlib import Path
from app.core.errors import AppError
from app.dtos.contracts import ResultDTO, StreamDTO
from app.utils.files import FOLDER, GOOGLE_PREFIX, OFFICE_TYPES, extension, disposition, is_text
from app.models.records import ManagedStream

logger = logging.getLogger(__name__)


def local_chunks(path, cleanup=None):
    """Tạo stream local có close chủ động kể cả client ngắt trước byte đầu tiên."""
    async def chunks():
        """Đọc chunk trong worker thread, đóng handle trong finally khi hủy."""
        file = await asyncio.to_thread(path.open, 'rb')
        try:
            while chunk := await asyncio.to_thread(file.read, 256 * 1024):
                yield chunk
        finally:
            await asyncio.to_thread(file.close)

    async def close():
        """Chạy cleanup trong event loop để khóa asyncio được giải phóng đúng thread."""
        if cleanup:
            cleanup()

    return ManagedStream(chunks(), close)


class PreviewService:
    """Định tuyến viewer và quản lý dữ liệu dẫn xuất; không sửa file Office gốc."""
    def __init__(self, settings, mongo, drive, scope):
        """Tạo khóa cache/system; mọi đường dẫn cache được hash từ ID/version."""
        self.settings, self.mongo, self.drive, self.scope = settings, mongo, drive, scope
        self.cache = settings.local_data_dir / 'cache'
        self.lock = asyncio.Lock()
        self.active = {}

    async def system_folder(self):
        """Tìm folder hệ thống trong root, phục hồi ID Mongo nếu cần rồi tạo khi thiếu."""
        candidates = await self.drive.children(self.settings.google_drive_root_folder_id)
        folder = next((f for f in candidates if self.scope.system(f) and f['mimeType'] == FOLDER), None)
        if folder is None:
            folder = await self.drive.create_folder(self.settings.drive_system_folder_name, self.settings.google_drive_root_folder_id, system=True)
        await self.mongo.put('system_state', 'drive_system_folder', {'folder_id': folder['id']})
        return folder['id']

    async def describe(self, request):
        """Service chọn loại viewer theo MIME + extension và cấu hình từng loại Office."""
        file, _ = await self.scope.file(request.workspace_id, request.file_id)
        mime, ext = file['mimeType'], extension(file['name'])
        kind = 'metadata'
        if mime.startswith(GOOGLE_PREFIX) and mime != FOLDER:
            kind = 'drive'
        elif mime == 'application/pdf' or ext == 'pdf':
            kind = 'pdf'
        elif ext in OFFICE_TYPES:
            kind = 'office' if self.settings.office_preview_rules.get(ext, 'pdf') == 'pdf' else 'drive'
        elif mime.startswith('image/'):
            kind = 'image'
        elif mime.startswith('video/'):
            kind = 'video'
        elif mime.startswith('audio/'):
            kind = 'audio'
        elif is_text(file) and int(file.get('size', 0)) <= self.settings.max_edit_file_size_mb * 1024 * 1024:
            kind = 'text'
        return ResultDTO(data={'kind': kind, 'preview_url': f"https://drive.google.com/file/d/{file['id']}/preview", 'edit_url': file.get('webViewLink') or f"https://drive.google.com/file/d/{file['id']}/view"})

    async def office_pdf(self, request):
        """Khóa cache theo phiên bản; lỗi convert/export trả mã để frontend fallback Drive."""
        file, _ = await self.scope.file(request.workspace_id, request.file_id)
        ext = extension(file['name'])
        if ext not in OFFICE_TYPES:
            raise AppError('unsupported_conversion', 422)
        key = hashlib.sha256(f"{file['id']}:{file.get('version', '')}".encode()).hexdigest()
        async with self.lock:
            self.cache.mkdir(parents=True, exist_ok=True)
            path = self.cache / f'{key}.pdf'
            if not path.exists():
                temporary, upstream, exported = None, None, None
                partial = self.cache / f'{key}.part'
                try:
                    system = await self.system_folder()
                    upstream = await self.drive.stream(file['id'])
                    temporary = await self.drive.upload(system, f'preview-{key}', file['mimeType'], int(file['size']), upstream.content, google_mime=OFFICE_TYPES[ext])
                    exported = await self.drive.stream(temporary['id'], export_mime='application/pdf')
                    with partial.open('wb') as output:
                        async for chunk in exported.content:
                            await asyncio.to_thread(output.write, chunk)
                    partial.replace(path)
                except BaseException as error:
                    partial.unlink(missing_ok=True)
                    if isinstance(error, asyncio.CancelledError):
                        raise
                    raise AppError('conversion_fallback', 422) from None
                finally:
                    if upstream:
                        await upstream.content.aclose()
                    if exported:
                        await exported.content.aclose()
                    if temporary:
                        try:
                            await self.drive.delete_temporary(temporary['id'])
                        except Exception:
                            logger.warning('Không xóa được bản chuyển đổi tạm; kiểm tra folder hệ thống trên Drive.')
            # Dọn LRU ngoài file đang phục vụ; một bản hiện tại được giữ đến khi stream hoàn tất.
            path.touch()
            total = sum(p.stat().st_size for p in self.cache.glob('*.pdf'))
            for other in sorted(self.cache.glob('*.pdf'), key=lambda p: p.stat().st_mtime):
                if total <= self.settings.pdf_cache_max_mb * 1024 * 1024:
                    break
                if other != path and not self.active.get(other, 0):
                    total -= other.stat().st_size
                    other.unlink(missing_ok=True)
            remove = self.settings.pdf_cache_max_mb == 0 or path.stat().st_size > self.settings.pdf_cache_max_mb * 1024 * 1024
            self.active[path] = self.active.get(path, 0) + 1

        def release_cache():
            """Không xóa PDF khi một response khác đang dùng cùng cache key."""
            self.active[path] -= 1
            if not self.active[path]:
                del self.active[path]
                if remove:
                    path.unlink(missing_ok=True)

        return StreamDTO(content=local_chunks(path, release_cache), headers={
            'Content-Type': 'application/pdf', 'Content-Length': str(path.stat().st_size), 'Content-Disposition': disposition(file['name'] + '.pdf', True), 'Cache-Control': 'private, no-store'})
