"""Hợp đồng Request/Response; Controller tạo Request, Service tạo Response."""
from collections.abc import AsyncIterator
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResultDTO(BaseModel):
    """Dữ liệu phản hồi cho các thao tác không cần schema phân trang."""
    data: Any = None


class FileDTO(BaseModel):
    """Metadata Drive công khai; không chứa token hoặc đường dẫn hệ thống."""
    id: str
    name: str
    mimeType: str
    size: str | None = None
    createdTime: str | None = None
    modifiedTime: str | None = None
    version: str | None = None
    webViewLink: str | None = None
    parents: list[str] = []
    trashed: bool = False
    permissions: list[dict] = []
    workspace_id: str | None = None
    workspace_name: str | None = None


class ListDTO(BaseModel):
    """Danh sách đã chuẩn hóa từ Service và breadcrumb đúng phạm vi."""
    files: list[FileDTO]
    breadcrumbs: list[FileDTO] = []


class NameRequest(BaseModel):
    """Tên file/folder hợp lệ; tránh path separator và ký tự điều khiển."""
    name: str = Field(min_length=1, max_length=240)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        """Trim tên → chặn tên đặc biệt và ký tự không an toàn cho archive."""
        value = value.strip()
        if not value or value in ('.', '..') or any(ord(c) < 32 or c in '/\\' for c in value):
            raise ValueError('Invalid file name')
        return value


class FileRequest(BaseModel):
    """Tham chiếu có Workspace bắt buộc cho mọi thao tác file."""
    workspace_id: str
    file_id: str


class FolderRequest(FileRequest, NameRequest):
    """Tạo hoặc đổi tên trong Workspace đã xác thực."""


class UploadRequest(FolderRequest):
    """Mở phiên upload; tổng file độc lập kích thước mỗi HTTP request."""
    size: int = Field(ge=0, le=5 * 1024 ** 4)
    mime: str = Field(default='application/octet-stream', min_length=1, max_length=200, pattern=r'^[\w.+-]+/[\w.+-]+$')


class UploadChunkRequest(BaseModel):
    """Vị trí và độ dài phần dữ liệu được Controller tạo từ request."""
    workspace_id: str
    upload_id: str
    offset: int = Field(ge=0)
    size: int = Field(ge=0, le=8 * 1024 * 1024)


class DeleteWorkspaceRequest(BaseModel):
    """Hai bước xóa gắn vào snapshot tên + số mục mà người dùng vừa xem."""
    workspace_id: str
    confirmation_name: str
    confirmation_token: str


class SettingsRequest(BaseModel):
    """Chỉ cho phép cài đặt có schema; không ghi body tùy ý vào MongoDB."""
    language: Literal['vi', 'en'] = 'vi'
    theme: Literal['light', 'dark', 'system'] = 'system'
    view: Literal['grid', 'list'] = 'list'
    workspace_sort: Literal['name', 'date', 'manual'] = 'name'
    direction: Literal['asc', 'desc'] = 'asc'


class OrderRequest(BaseModel):
    """Thứ tự Workspace kéo thả, giới hạn payload."""
    ids: list[str] = Field(max_length=10000)


class SaveRequest(FileRequest):
    """Nội dung editor kèm phiên bản mở và cách xử lý xung đột."""
    content: str
    version: str
    strategy: Literal['normal', 'overwrite', 'copy'] = 'normal'


class TransferRequest(FileRequest):
    """Kiểm tra nguồn và đích độc lập khi di chuyển/sao chép qua Workspace."""
    target_workspace_id: str
    target_folder_id: str
    mode: Literal['move', 'copy']


class PermissionRequest(BaseModel):
    """Chia sẻ chỉ nhận các role Drive được phép."""
    type: Literal['user', 'anyone'] = 'user'
    role: Literal['reader', 'commenter', 'writer'] = 'reader'
    email: str | None = Field(default=None, max_length=254)
    notify: bool = False


class StreamDTO(BaseModel):
    """Controller bọc luồng này thành StreamingResponse, không đọc hết vào RAM."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    content: AsyncIterator[bytes]
    headers: dict[str, str]
    status: int = 200
