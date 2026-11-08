"""DTO cho tín hiệu đồng bộ; chỉ chứa ID/phạm vi, không chứa nội dung hay credential."""
from typing import Literal
from pydantic import BaseModel, Field


class ChangeDTO(BaseModel):
    """Service công bố dữ liệu đã thay đổi; client tự đọc lại API đã phân quyền."""
    kind: Literal['files', 'workspaces', 'preferences', 'connection', 'reset', 'session'] = 'files'
    workspace_ids: list[str] = Field(default_factory=list, max_length=100)
    parent_ids: list[str] = Field(default_factory=list, max_length=100)
    file_ids: list[str] = Field(default_factory=list, max_length=100)
    tree: bool = False
    trash: bool = False
    # Audience là thông tin nội bộ: lọc trước khi tạo payload SSE cho browser.
    user_id: str | None = None
    device_id: str | None = None
    session_id: str | None = None


class CursorRequest(BaseModel):
    """Cursor được validate dù lấy từ header hoặc query fallback."""
    cursor: str = Field(default='', max_length=64, pattern=r'^(?:[a-f0-9]{32}:\d{1,20})?$')


class DriveNotificationRequest(BaseModel):
    """Chỉ chấp nhận header có giới hạn trước khi đối chiếu kênh webhook trong DB."""
    channel_id: str = Field(min_length=1, max_length=64)
    token: str = Field(min_length=1, max_length=256)
    resource_id: str = Field(min_length=1, max_length=256)
    state: str = Field(min_length=1, max_length=32)
    message_number: int = Field(ge=1, le=2 ** 63 - 1)
