"""Controller file/preview/share/archive, raw upload không dùng multipart spool."""
from fastapi import APIRouter, Body, Depends, Request, Query
from app.core.streaming import ManagedStreamingResponse
from app.core.dependencies import current_user, services, file_user
from app.dtos.contracts import FileRequest, FolderRequest, SaveRequest, TransferRequest, PermissionRequest, UploadRequest, UploadChunkRequest
from app.core.errors import AppError

router = APIRouter(dependencies=[Depends(file_user)])


def file_request(workspace_id, file_id):
    """Tạo DTO từ path, không lấy Workspace do body không tin cậy ghi đè."""
    return FileRequest(workspace_id=workspace_id, file_id=file_id)


def streaming(dto):
    """Bọc StreamDTO thành HTTP response và giữ status 206/Range từ upstream."""
    return ManagedStreamingResponse(dto)


@router.post('/workspaces/{workspace_id}/files/{file_id}/access')
async def media_access(workspace_id: str, file_id: str, request: Request):
    """Bearer + scope hợp lệ → cookie httpOnly giới hạn đúng path file trong 30 phút."""
    from fastapi.responses import JSONResponse
    await services(request).files.metadata(file_request(workspace_id, file_id))
    result = await services(request).auth.media_grant(request.headers['authorization'][7:], workspace_id, file_id)
    response = JSONResponse({'data': {'ready': True}})
    response.set_cookie('myhub_media', result.data['token'], httponly=True, samesite='lax',
        secure=request.app.state.settings.cookie_secure, max_age=1800, path=f'/api/v1/workspaces/{workspace_id}/files/{file_id}')
    return response


@router.get('/archive-formats')
async def formats(request: Request):
    """UI biết định dạng nào cần cài thêm công cụ trước khi cho tải."""
    return services(request).archive.capabilities()


@router.get('/trash')
async def trash_workspaces(request: Request):
    """Danh sách Workspace trong thùng rác ở cấp toàn cục."""
    return await services(request).files.trash_list()


@router.get('/workspaces/{workspace_id}/trash')
async def trash_files(workspace_id: str, request: Request):
    """Thùng rác file được giới hạn theo Workspace đang chọn."""
    return await services(request).files.trash_list(workspace_id)


@router.get('/workspaces/{workspace_id}/files')
async def listing(workspace_id: str, request: Request, parent_id: str | None = None, search: str = Query('', max_length=240), sort: str = 'name', direction: str = 'asc'):
    """Chuyển query sang Service; folder mặc định là Workspace root."""
    return await services(request).files.listing(workspace_id, parent_id or workspace_id, search, sort, direction)


@router.post('/workspaces/{workspace_id}/folders', status_code=201)
async def folder(workspace_id: str, request: Request, body: dict = Body(...)):
    """Tạo DTO từ parent/name do người dùng chọn rồi gọi Service."""
    dto = FolderRequest(workspace_id=workspace_id, file_id=body.get('parent_id', workspace_id), name=body.get('name', ''))
    return await services(request).files.folder(dto)


@router.post('/workspaces/{workspace_id}/upload', status_code=201)
async def upload(workspace_id: str, request: Request, parent_id: str, name: str, size: int = Query(ge=0)):
    """Raw body được stream tới Drive; Content-Length phải khớp size đã khai báo."""
    if request.headers.get('content-length') != str(size):
        raise AppError('content_length_required', 411)
    dto = FolderRequest(workspace_id=workspace_id, file_id=parent_id, name=name)
    return await services(request).files.upload(dto, request.headers.get('content-type', 'application/octet-stream'), size, request.stream())


@router.post('/workspaces/{workspace_id}/uploads', status_code=201)
async def upload_begin(workspace_id: str, request: Request, body: dict = Body(...), user=Depends(current_user)):
    """Tạo DTO mở phiên, không nhận ID người dùng từ body."""
    dto = UploadRequest(workspace_id=workspace_id, file_id=body.get('parent_id', workspace_id),
        name=body.get('name', ''), size=body.get('size'), mime=body.get('mime', 'application/octet-stream'))
    return await services(request).uploads.begin(dto, user['id'])


@router.get('/workspaces/{workspace_id}/uploads/{upload_id}')
async def upload_status(workspace_id: str, upload_id: str, request: Request, user=Depends(current_user)):
    """Đối chiếu byte đã nhận sau khi reload hoặc đứt kết nối."""
    return await services(request).uploads.status(workspace_id, upload_id, user['id'])


@router.put('/workspaces/{workspace_id}/uploads/{upload_id}')
async def upload_chunk(workspace_id: str, upload_id: str, request: Request, offset: int = Query(ge=0), user=Depends(current_user)):
    """Content-Length giới hạn từng phần; HTTP body không chứa cả file lớn."""
    length = request.headers.get('content-length', '')
    if not length.isdecimal():
        raise AppError('content_length_required', 411)
    dto = UploadChunkRequest(workspace_id=workspace_id, upload_id=upload_id, offset=offset, size=int(length))
    return await services(request).uploads.chunk(dto, user['id'], request.stream())


@router.delete('/workspaces/{workspace_id}/uploads/{upload_id}')
async def upload_cancel(workspace_id: str, upload_id: str, request: Request, user=Depends(current_user)):
    """Nút hủy thu hồi phiên, không xóa nội dung Drive đã có."""
    return await services(request).uploads.cancel(workspace_id, upload_id, user['id'])


@router.get('/workspaces/{workspace_id}/files/{file_id}')
async def metadata(workspace_id: str, file_id: str, request: Request):
    """Trả metadata file đã kiểm tra phạm vi."""
    return await services(request).files.metadata(file_request(workspace_id, file_id))


@router.patch('/workspaces/{workspace_id}/files/{file_id}')
async def rename(workspace_id: str, file_id: str, request: Request, body: dict = Body(...)):
    """Chỉ nhận tên mới, không cho body cập nhật trực tiếp metadata Drive."""
    dto = FolderRequest(workspace_id=workspace_id, file_id=file_id, name=body.get('name', ''))
    return await services(request).files.rename(dto)


@router.delete('/workspaces/{workspace_id}/files/{file_id}')
async def trash(workspace_id: str, file_id: str, request: Request):
    """Soft-delete bằng Drive trash, không xóa vĩnh viễn dữ liệu người dùng."""
    return await services(request).files.trash(file_request(workspace_id, file_id))


@router.post('/workspaces/{workspace_id}/files/{file_id}/restore')
async def restore(workspace_id: str, file_id: str, request: Request):
    """Khôi phục file hoặc chính Workspace root sau kiểm tra scope."""
    return await services(request).files.restore(file_request(workspace_id, file_id))


@router.post('/workspaces/{workspace_id}/files/{file_id}/transfer')
async def transfer(workspace_id: str, file_id: str, request: Request, body: dict = Body(...)):
    """DTO luôn lấy nguồn từ path, đích và mode từ body có schema."""
    dto = TransferRequest(**{**body, 'workspace_id': workspace_id, 'file_id': file_id})
    return await services(request).files.transfer(dto)


@router.get('/workspaces/{workspace_id}/files/{file_id}/content')
async def content(workspace_id: str, file_id: str, request: Request, inline: bool = False):
    """Stream nguồn, hỗ trợ HTTP Range mà không đọc file lớn vào RAM."""
    return streaming(await services(request).files.download(file_request(workspace_id, file_id), request.headers.get('range'), inline))


@router.get('/workspaces/{workspace_id}/files/{file_id}/text')
async def text(workspace_id: str, file_id: str, request: Request):
    """Trả text UTF-8 và version để frontend mở CodeMirror."""
    return await services(request).files.text(file_request(workspace_id, file_id))


@router.put('/workspaces/{workspace_id}/files/{file_id}/text')
async def save(workspace_id: str, file_id: str, request: Request, body: dict = Body(...)):
    """Tạo SaveRequest gồm version và chiến lược xử lý conflict."""
    dto = SaveRequest(**{**body, 'workspace_id': workspace_id, 'file_id': file_id})
    return await services(request).files.save(dto)


@router.get('/workspaces/{workspace_id}/files/{file_id}/preview')
async def preview(workspace_id: str, file_id: str, request: Request):
    """Trả loại viewer và link Drive; không làm chuyển đổi khi chưa mở viewer."""
    return await services(request).preview.describe(file_request(workspace_id, file_id))


@router.get('/workspaces/{workspace_id}/files/{file_id}/pdf')
async def pdf(workspace_id: str, file_id: str, request: Request):
    """Office conversion stream; lỗi có mã riêng để UI fallback /preview."""
    return streaming(await services(request).preview.office_pdf(file_request(workspace_id, file_id)))


@router.get('/workspaces/{workspace_id}/files/{file_id}/archive')
async def archive(workspace_id: str, file_id: str, request: Request, format: str = 'zip'):
    """Tải folder đã đóng gói và tự dọn workspace tạm khi đóng stream."""
    return streaming(await services(request).archive.archive(file_request(workspace_id, file_id), format))


@router.get('/workspaces/{workspace_id}/files/{file_id}/revisions')
async def revisions(workspace_id: str, file_id: str, request: Request):
    """Lịch sử phiên bản có phân loại native Google và file binary."""
    return await services(request).files.revisions(file_request(workspace_id, file_id))


@router.get('/workspaces/{workspace_id}/files/{file_id}/revisions/{revision_id}/content')
async def revision_download(workspace_id: str, file_id: str, revision_id: str, request: Request):
    """Stream revision cũ qua cùng phạm vi kiểm tra như download hiện tại."""
    return streaming(await services(request).files.download(file_request(workspace_id, file_id), revision_id=revision_id))


@router.post('/workspaces/{workspace_id}/files/{file_id}/revisions/{revision_id}/restore')
async def revision_restore(workspace_id: str, file_id: str, revision_id: str, request: Request, body: dict = Body(...)):
    """Chỉ phục hồi nếu version frontend vừa xem còn khớp Drive."""
    return await services(request).files.restore_revision(file_request(workspace_id, file_id), revision_id, str(body.get('version', '')))


@router.get('/workspaces/{workspace_id}/files/{file_id}/permissions')
async def permissions(workspace_id: str, file_id: str, request: Request):
    """Đọc quyền và link Drive cho hộp thoại chia sẻ."""
    return await services(request).sharing.listing(file_request(workspace_id, file_id))


@router.post('/workspaces/{workspace_id}/files/{file_id}/permissions')
async def permission_create(workspace_id: str, file_id: str, request: Request, body: dict = Body(...)):
    """DTO email/type/role/notify được tạo tại Controller rồi chuyển xuống Service."""
    return await services(request).sharing.create(file_request(workspace_id, file_id), PermissionRequest(**body))


@router.patch('/workspaces/{workspace_id}/files/{file_id}/permissions/{permission_id}')
async def permission_update(workspace_id: str, file_id: str, permission_id: str, request: Request, body: dict = Body(...)):
    """Chỉ cập nhật role được schema cho phép, không đổi owner."""
    return await services(request).sharing.mutate(file_request(workspace_id, file_id), permission_id, PermissionRequest(**body))


@router.delete('/workspaces/{workspace_id}/files/{file_id}/permissions/{permission_id}')
async def permission_delete(workspace_id: str, file_id: str, permission_id: str, request: Request):
    """Gỡ quyền cụ thể; Service kiểm tra quyền owner và phạm vi file."""
    return await services(request).sharing.mutate(file_request(workspace_id, file_id), permission_id)
