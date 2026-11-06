"""Điểm khởi động FastAPI; ghép dependency và ánh xạ lỗi tại biên HTTP."""
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from types import SimpleNamespace
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from pymongo.errors import PyMongoError
from app.config.settings import get_settings
from app.core.errors import AppError
from app.repositories.mongo import MongoRepository
from app.repositories.drive import DriveRepository
from app.repositories.oauth import OAuthRepository
from app.services.auth import AuthService
from app.services.scope import ScopeService
from app.services.workspaces import WorkspaceService
from app.services.files import FileService
from app.services.sharing import SharingService
from app.services.preview import PreviewService
from app.services.archive import ArchiveService
from app.services.uploads import UploadService
from app.controllers import auth, files, workspaces


def create_app(settings=None, service_override=None):
    """App factory cho runtime và test; injection fake không cần Mongo/Drive thật."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app):
        """Mở pool → tạo Service container → giải phóng tất cả pool khi dừng."""
        if service_override:
            app.state.services = service_override
            yield
            return
        mongo = MongoRepository(settings)
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15), follow_redirects=False) as http:
            drive = DriveRepository(settings, mongo, http)
            scope = ScopeService(settings, drive)
            app.state.services = SimpleNamespace(
                auth=AuthService(settings, mongo, OAuthRepository(settings, http), drive),
                workspaces=WorkspaceService(settings, mongo, drive, scope),
                files=FileService(settings, drive, scope), sharing=SharingService(drive, scope),
                preview=PreviewService(settings, mongo, drive, scope), archive=ArchiveService(settings, drive, scope),
                uploads=UploadService(settings, mongo, drive, scope), mongo=mongo)
            try:
                await mongo.initialize()
                yield
            finally:
                await mongo.close()

    app = FastAPI(title='MyHub API', version='0.1.0', lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
        allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], allow_headers=['Authorization', 'Content-Type', 'Range'],
        expose_headers=['Content-Disposition', 'Content-Length', 'Content-Range', 'Accept-Ranges'])

    @app.middleware('http')
    async def response_headers(request: Request, call_next):
        """Chặn JSON quá lớn theo Content-Length; mọi API phản hồi đều private/no-store."""
        length = request.headers.get('content-length', '0')
        if not request.url.path.endswith('/upload') and (not length.isdecimal() or int(length) > 24 * 1024 * 1024):
            return JSONResponse({'error': {'code': 'request_too_large'}}, status_code=413)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.exception_handler(AppError)
    async def domain_error(request, error):
        """Chuyển lỗi miền sang HTTP JSON thống nhất, không lộ nội dung upstream."""
        return JSONResponse({'error': {'code': error.code, 'message': error.message}}, status_code=error.status)

    @app.exception_handler(ValidationError)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        """Bỏ input khỏi chi tiết validation để không phản chiếu nội dung nhạy cảm."""
        return JSONResponse({'error': {'code': 'validation_error', 'fields': [str(e['loc']) for e in error.errors()]}}, status_code=422)

    @app.exception_handler(PyMongoError)
    async def mongo_error(request, error):
        """Lỗi DB chỉ hiển thị mã phục hồi, không lộ connection string."""
        return JSONResponse({'error': {'code': 'database_unavailable'}}, status_code=503)

    @app.exception_handler(httpx.HTTPError)
    async def upstream_error(request, error):
        """Không để URL token/code hoặc header upstream xuất hiện trong lỗi trả về."""
        return JSONResponse({'error': {'code': 'upstream_unavailable'}}, status_code=502)

    @app.get('/api/v1/health')
    async def health():
        """Liveness không trả bí mật; startup chỉ thành công sau Mongo ping và index."""
        release_file = Path(__file__).resolve().parents[2] / 'RELEASE'
        return {'status': 'ok', 'version': '0.1.0', 'release': release_file.read_text().strip() if release_file.is_file() else 'local'}

    for controller in (auth.router, workspaces.router, files.router):
        app.include_router(controller, prefix='/api/v1')
    return app


# Uvicorn dùng --factory app.main:create_app để cấu hình được kiểm tra lúc khởi chạy.
