"""Workspace là folder con của root; Mongo chỉ giữ cài đặt và thứ tự."""
from datetime import datetime, timedelta, timezone
import jwt
from app.core.errors import AppError
from app.dtos.contracts import FileDTO, ListDTO, ResultDTO
from app.utils.files import FOLDER


class WorkspaceService:
    """Nghiệp vụ chọn/tạo/đổi tên/xóa và sắp xếp Workspace."""
    def __init__(self, settings, mongo, drive, scope):
        """Nhận repository và scope, không phụ thuộc FastAPI."""
        self.settings, self.mongo, self.drive, self.scope = settings, mongo, drive, scope
        self.sync = None

    @staticmethod
    def preference_key(user_id, device_id=None):
        """Giữ key cũ cho client cũ; browser mới có vùng cài đặt và thứ tự độc lập."""
        return f'{user_id}:device:{device_id}' if device_id else user_id

    async def listing(self, user_id, device_id=None):
        """Drive → lọc Workspace → áp dụng cài đặt Mongo → tạo ListDTO."""
        items = [f for f in await self.drive.children(self.settings.google_drive_root_folder_id) if f['mimeType'] == FOLDER and not self.scope.system(f)]
        key = self.preference_key(user_id, device_id)
        preferences = (await self.mongo.get('user_settings', key)) or {}
        order = (await self.mongo.get('workspace_orders', key) or {}).get('ids', [])
        mode, reverse = preferences.get('workspace_sort', 'name'), preferences.get('direction') == 'desc'
        if mode == 'manual':
            positions = {value: i for i, value in enumerate(order)}
            items.sort(key=lambda f: (positions.get(f['id'], len(order)), f['name'].casefold()))
        else:
            items.sort(key=lambda f: f.get('createdTime', '') if mode == 'date' else f['name'].casefold(), reverse=reverse)
        return ListDTO(files=[FileDTO(**f) for f in items])

    async def unique(self, name, except_id=None):
        """Không tạo Workspace trùng tên hoặc trùng tên hệ thống."""
        if name == self.settings.drive_system_folder_name:
            raise AppError('reserved_name', 409)
        siblings = await self.drive.children(self.settings.google_drive_root_folder_id)
        if any(f['id'] != except_id and f['name'].casefold() == name.casefold() and f['mimeType'] == FOLDER for f in siblings):
            raise AppError('duplicate_workspace', 409)

    async def create(self, request):
        """Validate tên duy nhất → tạo folder root → trả FileDTO."""
        await self.unique(request.name)
        file = await self.drive.create_folder(request.name, self.settings.google_drive_root_folder_id)
        if self.sync:
            await self.sync.changed(kind='workspaces', workspace_ids=[file['id']])
        return FileDTO(**file)

    async def rename(self, workspace_id, request):
        """Kiểm tra Workspace và trùng tên rồi cập nhật chính folder Drive."""
        await self.scope.workspace(workspace_id)
        await self.unique(request.name, workspace_id)
        file = await self.drive.update(workspace_id, {'name': request.name})
        if self.sync:
            await self.sync.changed(kind='workspaces', workspace_ids=[workspace_id], tree=True)
        return FileDTO(**file)

    async def impact(self, workspace_id, user_id):
        """Bước 1 xóa: đếm cây hiện tại và ký snapshot xác nhận có hạn 5 phút."""
        file = await self.scope.workspace(workspace_id)
        children = await self.scope.descendants(workspace_id)
        signature = self.snapshot(children)
        token = jwt.encode({'sub': user_id, 'workspace': workspace_id, 'name': file['name'], 'snapshot': signature,
            'type': 'delete_workspace', 'exp': datetime.now(timezone.utc) + timedelta(minutes=5)}, self.settings.jwt_secret_key, algorithm='HS256')
        return ResultDTO(data={'name': file['name'], 'count': len(children), 'confirmation_token': token})

    @staticmethod
    def snapshot(children):
        """Hash cả ID/version để thay đổi giữa hai bước buộc người dùng xác nhận lại."""
        from app.services.auth import digest
        return digest('|'.join(sorted(f"{f['id']}:{f.get('version', '')}" for f in children)))

    async def delete(self, request, user_id):
        """Bước 2: kiểm tra token/tên/snapshot → chỉ chuyển Workspace vào thùng rác."""
        try:
            payload = jwt.decode(request.confirmation_token, self.settings.jwt_secret_key, algorithms=['HS256'])
        except jwt.PyJWTError:
            raise AppError('confirmation_expired', 409) from None
        file = await self.scope.workspace(request.workspace_id)
        if any((payload.get('sub') != user_id, payload.get('type') != 'delete_workspace', payload.get('workspace') != request.workspace_id,
                payload.get('name') != file['name'], request.confirmation_name != file['name'],
                payload.get('snapshot') != self.snapshot(await self.scope.descendants(request.workspace_id)))):
            raise AppError('confirmation_changed', 409)
        await self.drive.update(request.workspace_id, {'trashed': True})
        if self.sync:
            await self.sync.changed(kind='workspaces', workspace_ids=[request.workspace_id], tree=True, trash=True)
        return ResultDTO(data={'trashed': True})

    async def settings_get(self, user_id, device_id=None):
        """Trả cài đặt riêng của browser; không kế thừa theme chia sẻ từ thiết bị khác."""
        from app.dtos.contracts import SettingsRequest
        values = await self.mongo.get('user_settings', self.preference_key(user_id, device_id)) or {}
        return ResultDTO(data=SettingsRequest(**values).model_dump())

    async def settings_save(self, user_id, request, device_id=None):
        """Lưu duy nhất các trường có trong SettingsRequest."""
        await self.mongo.put('user_settings', self.preference_key(user_id, device_id), request.model_dump())
        if self.sync:
            await self.sync.changed(kind='preferences', user_id=user_id, device_id=device_id or 'legacy')
        return ResultDTO(data=request.model_dump())

    async def order(self, user_id, request, device_id=None):
        """Chỉ nhận ID Workspace thật và không lặp rồi lưu thứ tự MongoDB."""
        items = await self.listing(user_id, device_id)
        allowed = {f.id for f in items.files}
        if len(set(request.ids)) != len(request.ids) or any(value not in allowed for value in request.ids):
            raise AppError('invalid_workspace_order')
        await self.mongo.put('workspace_orders', self.preference_key(user_id, device_id), {'ids': request.ids})
        if self.sync:
            await self.sync.changed(kind='preferences', user_id=user_id, device_id=device_id or 'legacy')
        return ResultDTO(data={'saved': True})
