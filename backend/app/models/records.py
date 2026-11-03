"""Các model nội bộ không phụ thuộc HTTP hoặc DTO."""
from dataclasses import dataclass
from collections.abc import AsyncIterator
import anyio


class ManagedStream:
    """Iterator có close tường minh, giải phóng cả tài nguyên mở trước lần yield đầu."""
    def __init__(self, iterator, close):
        """Gắn iterator với callback async dọn dẹp, đảm bảo gọi tối đa một lần."""
        self.iterator, self.close_callback, self.closed = iterator, close, False

    def __aiter__(self):
        """Trả chính iterator để StreamingResponse dùng async for."""
        return self

    async def __anext__(self):
        """Đóng tài nguyên khi EOF hoặc lỗi/hủy trong thao tác đọc."""
        if self.closed:
            raise StopAsyncIteration
        try:
            return await self.iterator.__anext__()
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self):
        """Idempotent; vẫn chạy callback dù async generator chưa được bắt đầu."""
        if not self.closed:
            self.closed = True
            with anyio.CancelScope(shield=True):
                try:
                    await self.iterator.aclose()
                finally:
                    await self.close_callback()


@dataclass
class StreamRecord:
    """Luồng nguồn dữ liệu; Service dùng để tạo DTO stream trả Controller."""
    content: AsyncIterator[bytes]
    headers: dict[str, str]
    status: int = 200
