"""HTTP streaming luôn đóng nguồn kể cả socket ngắt hoặc body chưa được đọc."""
import anyio
from fastapi.responses import StreamingResponse


class ManagedStreamingResponse(StreamingResponse):
    """Đóng StreamDTO trong finally thay vì phụ thuộc background task chạy thành công."""
    def __init__(self, dto):
        """Controller truyền DTO, response giữ iterator và header mà Service tạo."""
        self.source = dto.content
        super().__init__(dto.content, status_code=dto.status, headers=dto.headers)

    async def __call__(self, scope, receive, send):
        """Shield cleanup khỏi cancellation của request để upstream/tmp không bị bỏ quên."""
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self.source.aclose()
