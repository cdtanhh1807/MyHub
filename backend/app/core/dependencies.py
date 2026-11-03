"""HTTP dependency ở rìa hệ thống; Service không biết cookie/header."""
import re
from fastapi import Request
from app.core.errors import AppError


def services(request: Request):
    """Lấy container được tạo trong lifespan, thuận tiện thay fake khi test."""
    return request.app.state.services


async def current_user(request: Request):
    """API nghiệp vụ bắt buộc Bearer token; cookie chỉ dùng tại auth endpoints."""
    authorization = request.headers.get('Authorization', '')
    if not authorization.startswith('Bearer '):
        raise AppError('unauthorized', 401)
    return await services(request).auth.authenticate(authorization[7:])


def check_origin(request: Request):
    """Bảo vệ refresh/logout dùng cookie trước CSRF; chỉ nhận origin đã cấu hình."""
    settings = request.app.state.settings
    if request.headers.get('origin') not in {*settings.cors_origins, settings.frontend_url, settings.backend_url}:
        raise AppError('invalid_origin', 403)


async def file_user(request: Request):
    """Media GET dùng cookie phạm vi một file; các API khác vẫn bắt buộc Bearer."""
    if request.headers.get('Authorization', '').startswith('Bearer '):
        return await current_user(request)
    match = re.fullmatch(r'/api/v1/workspaces/([\w-]+)/files/([\w-]+)/(?:content|pdf|archive|revisions/[\w-]+/content)', request.url.path)
    if request.method != 'GET' or not match:
        raise AppError('unauthorized', 401)
    return await services(request).auth.media_user(request.cookies.get('myhub_media', ''), match[1], match[2])
