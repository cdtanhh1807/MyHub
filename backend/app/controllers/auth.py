"""Controller auth: chuyển HTTP/cookie thành input cho Service và xử lý redirect."""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from app.core.dependencies import services, current_user, check_origin
from app.core.errors import AppError
from app.services.auth import digest

router = APIRouter()
REFRESH_COOKIE = 'myhub_refresh'
OAUTH_COOKIE = 'myhub_oauth'
COOKIE_PATH = '/api/v1/auth'


def cookie(response, name, value, request, age):
    """Cookie httpOnly/SameSite và Secure theo cấu hình; không chứa access JWT."""
    response.set_cookie(name, value, httponly=True, secure=request.app.state.settings.cookie_secure,
        samesite='lax', path=COOKIE_PATH, max_age=age)


@router.get('/auth/{provider}/login')
async def login(provider: str, request: Request):
    """Bắt đầu đăng nhập Google/GitHub; không cho xin Drive khi chưa có phiên."""
    if provider not in ('google', 'github'):
        raise AppError('unknown_provider', 404)
    result = await services(request).auth.begin(provider)
    response = RedirectResponse(result.data['url'])
    cookie(response, OAUTH_COOKIE, result.data['browser'], request, 600)
    return response


@router.post('/drive-connection/authorize')
async def connect_drive(request: Request, user=Depends(current_user)):
    """Người đăng nhập mới được xin quyền Drive; trả URL để frontend điều hướng."""
    result = await services(request).auth.begin('drive', user)
    response = JSONResponse({'data': {'url': result.data['url']}})
    cookie(response, OAUTH_COOKIE, result.data['browser'], request, 600)
    return response


@router.get('/auth/{provider}/callback')
async def callback(provider: str, request: Request, state: str = '', code: str = '', error: str = ''):
    """Callback không đưa token vào URL; chỉ set refresh cookie rồi về frontend."""
    auth, settings = services(request).auth, request.app.state.settings
    try:
        if error or not code or not state:
            raise AppError('oauth_cancelled', 401)
        user = None
        if provider == 'drive':
            user = await auth.user_for_session(digest(request.cookies.get(REFRESH_COOKIE, '')))
        result = await auth.callback(provider, state, request.cookies.get(OAUTH_COOKIE, ''), code, user)
        response = RedirectResponse(settings.frontend_url, status_code=303)
        if 'refresh_token' in result.data:
            cookie(response, REFRESH_COOKIE, result.data['refresh_token'], request, settings.refresh_token_expire_days * 86400)
    except AppError as failure:
        response = RedirectResponse(f'{settings.frontend_url}/?error={failure.code}', status_code=303)
    response.delete_cookie(OAUTH_COOKIE, path=COOKIE_PATH)
    return response


@router.post('/auth/refresh')
async def refresh(request: Request):
    """Xoay refresh cookie và trả access JWT trong JSON để lưu chỉ trong RAM."""
    check_origin(request)
    result = await services(request).auth.refresh(request.cookies.get(REFRESH_COOKIE, ''))
    data = dict(result.data)
    secret = data.pop('refresh_token')
    response = JSONResponse({'data': data})
    cookie(response, REFRESH_COOKIE, secret, request, request.app.state.settings.refresh_token_expire_days * 86400)
    return response


@router.post('/auth/logout')
async def logout(request: Request):
    """Thu hồi session phía DB → xóa refresh cookie phía trình duyệt."""
    check_origin(request)
    result = await services(request).auth.logout(request.cookies.get(REFRESH_COOKIE, ''))
    response = JSONResponse(result.model_dump())
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return response


@router.get('/auth/me')
async def me(request: Request, user=Depends(current_user)):
    """Trả profile hiện tại, lọc các trường nội bộ của MongoDB."""
    return await services(request).auth.profile(user)


@router.get('/drive-connection')
async def connection(request: Request, user=Depends(current_user)):
    """Hiển thị tình trạng credential Drive cho tài khoản Google hoặc GitHub."""
    return await services(request).auth.connection()
