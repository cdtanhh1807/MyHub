"""Nghiệp vụ quyền chia sẻ với Google Drive link làm nguồn truy cập."""
import re
from app.core.errors import AppError
from app.dtos.contracts import ResultDTO
from app.utils.files import FOLDER


class SharingService:
    """Mọi thay đổi quyền đều phải kiểm tra file thuộc Workspace trước."""
    def __init__(self, drive, scope):
        """Nhận adapter Drive và lớp kiểm tra cây thư mục."""
        self.drive, self.scope = drive, scope

    async def listing(self, request):
        """Danh sách quyền hiện tại và link Drive để sao chép ngay trong app."""
        file, _ = await self.scope.file(request.workspace_id, request.file_id)
        fallback = f"https://drive.google.com/drive/folders/{file['id']}" if file['mimeType'] == FOLDER else f"https://drive.google.com/file/d/{file['id']}/view"
        return ResultDTO(data={'permissions': await self.drive.permissions(file['id']), 'url': file.get('webViewLink') or fallback})

    async def create(self, request, permission):
        """Mời email hoặc mở link; chỉ gửi email khi người dùng bật tùy chọn."""
        await self.scope.file(request.workspace_id, request.file_id)
        body = {'type': permission.type, 'role': permission.role}
        if permission.type == 'user':
            if not permission.email or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', permission.email):
                raise AppError('invalid_email')
            body['emailAddress'] = permission.email
        result = await self.drive.permissions(request.file_id, 'POST', body=body, notify=permission.notify if permission.type == 'user' else False)
        return ResultDTO(data=result)

    async def mutate(self, request, permission_id, permission=None):
        """Chặn sửa/xóa owner; quyền kế thừa do Drive quyết định và trả lỗi nếu không sửa được."""
        await self.scope.file(request.workspace_id, request.file_id)
        existing = next((p for p in await self.drive.permissions(request.file_id) if p['id'] == permission_id), None)
        if not existing or existing['role'] == 'owner':
            raise AppError('permission_not_editable', 403)
        result = await self.drive.permissions(request.file_id, 'PATCH' if permission else 'DELETE', permission_id,
            {'role': permission.role} if permission else None)
        return ResultDTO(data=result)
