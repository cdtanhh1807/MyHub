"""Endpoint đồng bộ nhẹ, bắt buộc xác thực như các API dữ liệu."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from app.core.streaming import ManagedStreamingResponse
from app.core.dependencies import current_user, device_id, services
from app.dtos.sync import CursorRequest, DriveNotificationRequest

router = APIRouter()


@router.get('/sync')
async def status(request: Request, user=Depends(current_user)):
    """Controller chuyển sang Service, không trả metadata hay credential."""
    return await request.app.state.sync.status()


@router.get('/sync/events')
async def events(request: Request, user=Depends(current_user), device=Depends(device_id)):
    """Dùng Bearer header hiện có; không chấp nhận token trong URL hay cookie media."""
    dto = CursorRequest(cursor=request.headers.get('last-event-id', ''))
    claims = services(request).auth.claims(request.headers['authorization'][7:])
    stream = request.app.state.sync.subscribe(user['id'], device or 'legacy', claims, dto.cursor)
    return ManagedStreamingResponse(stream)


@router.post('/sync/drive/webhook', status_code=204)
async def drive_webhook(request: Request):
    """Google không có Bearer của MyHub; Service xác minh channel token ngẫu nhiên thay thế."""
    dto = DriveNotificationRequest(channel_id=request.headers.get('x-goog-channel-id', ''),
        token=request.headers.get('x-goog-channel-token', ''), resource_id=request.headers.get('x-goog-resource-id', ''),
        state=request.headers.get('x-goog-resource-state', ''), message_number=request.headers.get('x-goog-message-number', '0'))
    await request.app.state.drive_sync.notification(dto)
    return Response(status_code=204)
