"""Lỗi nghiệp vụ độc lập HTTP; Controller/main chuyển thành phản hồi JSON."""


class AppError(Exception):
    """Mang mã lỗi ổn định để frontend dịch và xử lý đúng nhánh."""
    def __init__(self, code: str, status: int = 400, message: str = ''):
        """Ghi nhận lỗi miền → middleware ánh xạ sang status và nội dung an toàn."""
        self.code, self.status, self.message = code, status, message or code
        super().__init__(self.message)
