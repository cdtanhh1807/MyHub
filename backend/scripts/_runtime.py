"""Dependency CLI dùng cùng Settings/Repository như API, không cần backend đang chạy."""
import sys
from pathlib import Path
from contextlib import asynccontextmanager
import httpx

# Console/pipe Windows có thể là cp1252; CLI luôn xuất UTF-8 để in tiếng Việt an toàn.
for output_stream in (sys.stdout, sys.stderr):
    if hasattr(output_stream, 'reconfigure'):
        output_stream.reconfigure(encoding='utf-8')

# Script chạy trực tiếp → thêm backend vào module path, tương thích Windows/Ubuntu.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config.settings import get_settings
from app.repositories.mongo import MongoRepository
from app.repositories.drive import DriveRepository
from app.services.scope import ScopeService
from app.services.preview import PreviewService


@asynccontextmanager
async def runtime():
    """Mở DB và HTTP → tạo Drive adapter → luôn đóng tài nguyên khi CLI kết thúc."""
    settings = get_settings()
    mongo = MongoRepository(settings)
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as http:
        drive = DriveRepository(settings, mongo, http)
        preview = PreviewService(settings, mongo, drive, ScopeService(settings, drive))
        try:
            await mongo.initialize()
            yield settings, mongo, drive, preview
        finally:
            await mongo.close()
