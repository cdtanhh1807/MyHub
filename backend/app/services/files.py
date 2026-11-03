"""Quản lý file, editor, chuyển vị trí và lịch sử; luôn qua scope trước Drive."""
import asyncio
import re
from pathlib import PurePosixPath
from app.core.errors import AppError
from app.dtos.contracts import FileDTO, ListDTO, ResultDTO, StreamDTO, NameRequest
from app.utils.files import FOLDER, GOOGLE_PREFIX, disposition, is_text

NATIVE_EXPORTS = {
    'application/vnd.google-apps.document': ('application/pdf', '.pdf'),
    'application/vnd.google-apps.spreadsheet': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'),
    'application/vnd.google-apps.presentation': ('application/vnd.openxmlformats-officedocument.presentationml.presentation', '.pptx'),
}


async def bytes_stream(content):
    """Bọc nội dung editor giới hạn nhỏ thành iterator cho cùng pipeline upload."""
    yield content


class FileService:
    """Tạo DTO trả Controller; không nhận HTTP Request hoặc chạm database trực tiếp."""
    def __init__(self, settings, drive, scope):
        """Chuẩn bị khóa ghi editor trong tiến trình để chống hai save đồng thời."""
        self.settings, self.drive, self.scope = settings, drive, scope
        self.write_lock = asyncio.Lock()

    async def listing(self, workspace_id, folder_id, search='', sort='name', direction='asc'):
        """Lấy con folder hiện tại → tìm tên → sort (folder luôn trước) → DTO."""
        _, path = await self.scope.folder(workspace_id, folder_id)
        items = [f for f in await self.drive.children(folder_id) if not self.scope.system(f) and search.casefold() in f['name'].casefold()]
        keys = {'name': lambda f: f['name'].casefold(), 'type': lambda f: f['mimeType'], 'size': lambda f: int(f.get('size') or 0),
            'createdTime': lambda f: f.get('createdTime', ''), 'modifiedTime': lambda f: f.get('modifiedTime', '')}
        if sort not in keys or direction not in ('asc', 'desc'):
            raise AppError('invalid_sort')
        items.sort(key=keys[sort], reverse=direction == 'desc')
        items.sort(key=lambda f: f['mimeType'] != FOLDER)
        return ListDTO(files=[FileDTO(**f) for f in items], breadcrumbs=[FileDTO(**f) for f in path])

    async def metadata(self, request):
        """Đọc metadata trong Workspace được chọn, không lộ cha ngoài cây."""
        file, _ = await self.scope.file(request.workspace_id, request.file_id)
        return FileDTO(**file)

    async def folder(self, request):
        """Tạo thư mục con của folder đã qua scope, không cho ghi vào root hệ thống."""
        await self.scope.folder(request.workspace_id, request.file_id)
        return FileDTO(**await self.drive.create_folder(request.name, request.file_id))

    async def rename(self, request):
        """Workspace root dùng luồng riêng; file/folder con cập nhật tên tại chỗ."""
        await self.scope.file(request.workspace_id, request.file_id)
        if request.file_id == request.workspace_id:
            raise AppError('use_workspace_action')
        return FileDTO(**await self.drive.update(request.file_id, {'name': request.name}))

    async def trash(self, request):
        """Chỉ soft-delete file/folder con; xóa Workspace bắt buộc hai bước riêng."""
        await self.scope.file(request.workspace_id, request.file_id)
        if request.file_id == request.workspace_id:
            raise AppError('use_workspace_action')
        await self.drive.update(request.file_id, {'trashed': True})
        return ResultDTO(data={'trashed': True})

    async def upload(self, request, mime, size, content):
        """Kiểm tra đích → đếm byte khi stream upload → Drive giữ nội dung gốc."""
        await self.scope.folder(request.workspace_id, request.file_id)
        if size < 0:
            raise AppError('content_length_required', 411)

        async def checked():
            """Chặn request gửi quá Content-Length đã khai báo mà không buffer toàn file."""
            received = 0
            async for chunk in content:
                received += len(chunk)
                if received > size:
                    raise AppError('upload_size_mismatch')
                yield chunk
            if received != size:
                raise AppError('upload_size_mismatch')

        return FileDTO(**await self.drive.upload(request.file_id, request.name, mime, size, checked()))

    async def download(self, request, range_header=None, inline=False, revision_id=None):
        """Scope trước khi mở upstream; Range được giữ nguyên cho video/PDF."""
        file, _ = await self.scope.file(request.workspace_id, request.file_id)
        if file['mimeType'] == FOLDER:
            raise AppError('use_folder_archive')
        if range_header and (not re.fullmatch(r'bytes=\d*-\d*', range_header) or range_header == 'bytes=-'):
            raise AppError('invalid_range', 416)
        mime, suffix = NATIVE_EXPORTS.get(file['mimeType'], (None, ''))
        if revision_id and mime:
            raise AppError('native_revision_download_unsupported', 422)
        stream = await self.drive.stream(file['id'], range_header, mime, revision_id)
        return StreamDTO(content=stream.content, status=stream.status, headers={**stream.headers,
            'Content-Disposition': disposition(file['name'] + suffix, inline), 'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "sandbox; default-src 'none'"})

    async def text(self, request):
        """Chỉ đọc UTF-8/text nhỏ, kiểm tra lại version sau đọc để tránh snapshot lệch."""
        file, _ = await self.scope.file(request.workspace_id, request.file_id)
        limit = self.settings.max_edit_file_size_mb * 1024 * 1024
        if not is_text(file) or int(file.get('size', 0)) > limit:
            raise AppError('editor_unavailable', 413)
        stream = await self.drive.stream(file['id'])
        content = bytearray()
        try:
            async for chunk in stream.content:
                content.extend(chunk)
                if len(content) > limit:
                    raise AppError('editor_unavailable', 413)
        finally:
            await stream.content.aclose()
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            raise AppError('binary_or_non_utf8', 422) from None
        if '\x00' in text:
            raise AppError('binary_or_non_utf8', 422)
        latest = await self.drive.get(file['id'])
        if latest.get('version') != file.get('version'):
            raise AppError('conflict', 409)
        return ResultDTO(data={'content': text, 'version': file.get('version', ''), 'file': FileDTO(**file).model_dump()})

    async def save(self, request):
        """Kiểm tra phiên bản hiện tại; normal chặn stale, overwrite/copy là lựa chọn tường minh."""
        async with self.write_lock:
            file, _ = await self.scope.file(request.workspace_id, request.file_id)
            if not is_text(file):
                raise AppError('editor_unavailable', 422)
            content = request.content.encode('utf-8')
            if len(content) > self.settings.max_edit_file_size_mb * 1024 * 1024 or b'\x00' in content:
                raise AppError('editor_unavailable', 413)
            if request.strategy == 'normal' and str(file.get('version', '')) != request.version:
                raise AppError('conflict', 409)
            copying = request.strategy == 'copy'
            name = file['name']
            if copying:
                path = PurePosixPath(name)
                name = NameRequest(name=f'{path.stem} (copy){path.suffix}').name
            updated = await self.drive.upload(file['parents'][0], name, file['mimeType'], len(content), bytes_stream(content), None if copying else file['id'])
            return FileDTO(**updated)

    async def transfer(self, request):
        """Xác thực cả cây nguồn/đích; chặn Workspace root và chuyển folder vào chính con."""
        file, _ = await self.scope.file(request.workspace_id, request.file_id)
        _, target_path = await self.scope.folder(request.target_workspace_id, request.target_folder_id)
        if request.file_id == request.workspace_id or request.file_id in {f['id'] for f in target_path}:
            raise AppError('invalid_transfer')
        if request.mode == 'move':
            if request.target_folder_id in file.get('parents', []):
                return FileDTO(**file)
            result = await self.drive.update(file['id'], {}, addParents=request.target_folder_id, removeParents=','.join(file['parents']))
        else:
            if file['mimeType'] == FOLDER:
                raise AppError('folder_copy_not_supported', 422)
            result = await self.drive.copy(file['id'], request.target_folder_id, file['name'])
        return FileDTO(**result)

    async def trash_list(self, workspace_id=None):
        """Thùng rác toàn cục chỉ hiện Workspace; trong Workspace chỉ hiện mục thuộc cây đó."""
        items = []
        if workspace_id:
            await self.scope.workspace(workspace_id, allow_trashed=True)
        for file in await self.drive.trash_candidates():
            if not workspace_id:
                if file['mimeType'] == FOLDER and self.settings.google_drive_root_folder_id in file.get('parents', []) and not self.scope.system(file):
                    items.append(FileDTO(**file))
            else:
                try:
                    await self.scope.file(workspace_id, file['id'], allow_trashed=True)
                    items.append(FileDTO(**file))
                except AppError as error:
                    if error.code not in ('outside_workspace', 'shortcut_not_supported') and error.status != 404:
                        raise
        return ListDTO(files=items)

    async def restore(self, request):
        """Chỉ phục hồi đúng cây; nếu cha còn bị xóa thì yêu cầu phục hồi cha trước."""
        file, path = await self.scope.file(request.workspace_id, request.file_id, allow_trashed=True)
        if not file.get('trashed'):
            raise AppError('not_trashed')
        if any(item.get('trashed') for item in path[:-1]):
            raise AppError('restore_parent_first', 409)
        return FileDTO(**await self.drive.update(file['id'], {'trashed': False}))

    async def revisions(self, request):
        """Metadata lịch sử của Drive; native Google dùng trình chỉnh sửa gốc để phục hồi."""
        file, _ = await self.scope.file(request.workspace_id, request.file_id)
        if file['mimeType'].startswith(GOOGLE_PREFIX):
            return ResultDTO(data={'native': True, 'revisions': [], 'url': file.get('webViewLink')})
        return ResultDTO(data={'native': False, 'revisions': await self.drive.revisions(file['id'])})

    async def restore_revision(self, request, revision_id, expected_version):
        """Phục hồi revision nhị phân bằng update cùng ID, có kiểm tra version hiện tại."""
        async with self.write_lock:
            file, _ = await self.scope.file(request.workspace_id, request.file_id)
            if file['mimeType'].startswith(GOOGLE_PREFIX) or file.get('version') != expected_version:
                raise AppError('conflict', 409)
            revisions = await self.drive.revisions(file['id'])
            revision = next((r for r in revisions if r['id'] == revision_id), None)
            if not revision or 'size' not in revision:
                raise AppError('revision_unavailable', 404)
            stream = await self.drive.stream(file['id'], revision_id=revision_id)
            try:
                result = await self.drive.upload(file['parents'][0], file['name'], file['mimeType'], int(revision['size']), stream.content, file['id'])
                return FileDTO(**result)
            finally:
                await stream.content.aclose()
