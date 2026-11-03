"""Các quy tắc loại file và header dùng chung, không truy cập nguồn dữ liệu."""
import re
from pathlib import PurePosixPath
from urllib.parse import quote
from app.core.errors import AppError

FOLDER = 'application/vnd.google-apps.folder'
GOOGLE_PREFIX = 'application/vnd.google-apps.'
TEXT_EXTENSIONS = set('txt md csv json log yaml yml py js jsx ts tsx java html htm css scss sql xml sh bash ps1 toml ini cfg env c cpp h rs go rb php vue svelte dockerfile'.split())
OFFICE_TYPES = {
    'docx': 'application/vnd.google-apps.document',
    'xlsx': 'application/vnd.google-apps.spreadsheet',
    'xls': 'application/vnd.google-apps.spreadsheet',
    'pptx': 'application/vnd.google-apps.presentation',
    'ppt': 'application/vnd.google-apps.presentation',
}


def extension(name):
    """Lấy phần mở rộng chuẩn hóa để dùng cùng bảng viewer/editor."""
    return PurePosixPath(name).suffix.lower().lstrip('.') or name.lower()


def drive_id(value):
    """Chặn ID không hợp lệ trước khi đưa vào URL/query của Drive."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', value or ''):
        raise AppError('invalid_id')
    return value


def disposition(name, inline=False):
    """Mã hóa Unicode theo RFC5987 → tránh chèn header và giữ tên tiếng Việt."""
    return f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(name, safe='')}"


def is_text(file):
    """Nhận diện text theo MIME/phần mở rộng, từ chối file Google gốc."""
    return not file['mimeType'].startswith(GOOGLE_PREFIX) and (file['mimeType'].startswith('text/') or extension(file['name']) in TEXT_EXTENSIONS)
