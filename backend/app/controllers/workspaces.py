"""Controller Workspace/settings chỉ tạo DTO và gọi Service."""
from fastapi import APIRouter, Body, Depends, Request
from app.core.dependencies import current_user, services
from app.dtos.contracts import NameRequest, DeleteWorkspaceRequest, SettingsRequest, OrderRequest

router = APIRouter(dependencies=[Depends(current_user)])


@router.get('/workspaces')
async def listing(request: Request, user=Depends(current_user)):
    """Chuyển user ID đã xác thực xuống Service liệt kê Workspace."""
    return await services(request).workspaces.listing(user['id'])


@router.post('/workspaces', status_code=201)
async def create(request: Request, body: dict = Body(...)):
    """Controller tạo NameRequest trước khi gọi Service tạo folder Drive."""
    return await services(request).workspaces.create(NameRequest(**body))


@router.put('/workspaces/order')
async def order(request: Request, body: dict = Body(...), user=Depends(current_user)):
    """DTO thứ tự được kiểm tra tại biên HTTP rồi truyền xuống Service."""
    return await services(request).workspaces.order(user['id'], OrderRequest(**body))


@router.patch('/workspaces/{workspace_id}')
async def rename(workspace_id: str, request: Request, body: dict = Body(...)):
    """Đổi tên Workspace với DTO đã validate."""
    return await services(request).workspaces.rename(workspace_id, NameRequest(**body))


@router.get('/workspaces/{workspace_id}/delete-impact')
async def impact(workspace_id: str, request: Request, user=Depends(current_user)):
    """Bước đầu xóa: lấy ảnh hưởng và token snapshot cho hộp thoại xác nhận."""
    return await services(request).workspaces.impact(workspace_id, user['id'])


@router.delete('/workspaces/{workspace_id}')
async def delete(workspace_id: str, request: Request, body: dict = Body(...), user=Depends(current_user)):
    """Path ID do Controller ghi đè để body không thể chuyển Workspace khác."""
    dto = DeleteWorkspaceRequest(**{**body, 'workspace_id': workspace_id})
    return await services(request).workspaces.delete(dto, user['id'])


@router.get('/settings')
async def settings_get(request: Request, user=Depends(current_user)):
    """Đọc cài đặt đồng bộ của tài khoản đang đăng nhập."""
    return await services(request).workspaces.settings_get(user['id'])


@router.put('/settings')
async def settings_save(request: Request, body: dict = Body(...), user=Depends(current_user)):
    """Controller tạo SettingsRequest, không chuyển body tùy ý tới MongoDB."""
    return await services(request).workspaces.settings_save(user['id'], SettingsRequest(**body))
