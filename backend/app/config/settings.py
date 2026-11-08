"""Đọc cấu hình backend/.env, kiểm tra bí mật trước khi chạy ứng dụng."""
from pathlib import Path
from functools import lru_cache
from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Cấu hình typed; đường dẫn tương đối luôn tính từ backend, không phụ thuộc cwd."""
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / '.env', extra='ignore')
    jwt_secret_key: str = Field(min_length=32)
    encryption_key: str
    mongodb_uri: str
    mongodb_db_name: str = 'myhub'
    google_client_id: str = ''
    google_client_secret: str = ''
    github_client_id: str = ''
    github_client_secret: str = ''
    google_drive_root_folder_id: str = Field(min_length=1, pattern=r'^[A-Za-z0-9_-]{1,200}$')
    allowed_google_email: str = 'cdtanhh@gmail.com'
    allowed_github_username: str = 'cdtanhh1807'
    backend_url: str = 'http://localhost:8000'
    frontend_url: str = 'http://localhost:5173'
    cors_origins: list[str] = ['http://localhost:5173']
    cookie_secure: bool = False
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_expire_days: int = Field(default=30, ge=1, le=90)
    drive_system_folder_name: str = '.myhub-system'
    local_data_dir: Path = Path('../data')
    max_edit_file_size_mb: int = Field(default=5, ge=1, le=20)
    pdf_cache_max_mb: int = Field(default=256, ge=0)
    archive_max_mb: int = Field(default=2048, ge=1)
    archive_max_files: int = Field(default=10000, ge=1)
    archive_timeout_seconds: int = Field(default=1800, ge=30)
    seven_zip_path: str = '7z'
    rar_path: str = 'rar'
    sync_history_size: int = Field(default=256, ge=32, le=1024)
    sync_heartbeat_seconds: int = Field(default=25, ge=5, le=60)
    sync_max_connections_per_user: int = Field(default=8, ge=1, le=100)
    drive_sync_enabled: bool = True
    drive_sync_interval_seconds: int = Field(default=300, ge=60, le=3600)
    drive_webhook_enabled: bool = False
    office_preview_rules: dict[str, str] = {'docx': 'pdf', 'xlsx': 'pdf', 'xls': 'pdf', 'pptx': 'pdf', 'ppt': 'pdf'}

    @model_validator(mode='after')
    def validate_runtime(self):
        """Kiểm tra khóa mã hóa và HTTPS → chuẩn hóa thư mục runtime."""
        Fernet(self.encryption_key.encode())
        if self.frontend_url.startswith('https://') and not self.cookie_secure:
            raise ValueError('HTTPS requires COOKIE_SECURE=true')
        if self.drive_webhook_enabled:
            from urllib.parse import urlsplit
            target = urlsplit(self.backend_url)
            if target.scheme != 'https' or not target.hostname or target.username or target.password or target.query or target.fragment or target.path not in ('', '/'):
                raise ValueError('Drive webhook requires a public HTTPS BACKEND_URL without path/query')
        if not self.local_data_dir.is_absolute():
            self.local_data_dir = (BACKEND_DIR / self.local_data_dir).resolve()
        return self


@lru_cache
def get_settings() -> Settings:
    """Tái sử dụng một cấu hình đã validate trong mỗi tiến trình."""
    return Settings()
