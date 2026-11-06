# Quy ước làm việc với MyHub

## Giao tiếp và phạm vi

- Trao đổi với người dùng bằng tiếng Việt. Đọc `README.md` trước khi thay đổi cách cài đặt hoặc vận hành.
- Tự quyết định các chi tiết triển khai thông thường trong phạm vi được giao. Hỏi trước khi có quyết định quan trọng chưa được chốt, yêu cầu mâu thuẫn hoặc hành động không thể hoàn tác; không hỏi lại điều người dùng đã cho phép.
- Không tự commit hoặc push chỉ vì đã sửa code. Thực hiện khi người dùng yêu cầu commit/push hoặc đã giao trọn quy trình đó; khi được giao thì hoàn thành mà không hỏi lại từng bước.

## Git và GitHub

- Remote `origin`: `https://github.com/cdtanhh1807/MyHub.git`. Nhánh chính: `main`.
- Trước thao tác Git, kiểm tra nhánh hiện tại, trạng thái working tree và diff. Giữ nguyên thay đổi có sẵn của người dùng; không đưa thay đổi ngoài phạm vi vào commit.
- Với công việc code mới, tạo nhánh `feat/<ten-ngan>` cho tính năng hoặc `fix/<ten-ngan>` cho sửa lỗi, trừ khi người dùng chỉ định nhánh khác. Nếu đang làm tiếp cùng một nhiệm vụ, tiếp tục nhánh hiện tại.
- Trước khi cập nhật từ remote, fetch và kiểm tra quan hệ lịch sử. Với pull thông thường, ưu tiên `git pull --ff-only`. Không tự stash hoặc ghi đè thay đổi local. Nếu cần chọn cách xử lý lịch sử phân kỳ hay xung đột có ảnh hưởng hành vi, hỏi người dùng.
- Khi được yêu cầu commit/push: rà soát diff, chạy kiểm tra phù hợp, stage đúng file, tạo commit có thông điệp rõ ràng và push nhánh đang làm. Thiết lập upstream nếu nhánh chưa có; xác minh trạng thái sau push và báo nhánh cùng mã commit.
- Chỉ merge vào `main`, force-push, viết lại lịch sử đã push hoặc xóa nhánh remote khi người dùng yêu cầu rõ. Chỉ tạo Pull Request khi được yêu cầu hoặc nằm trong quy trình người dùng đã giao.
- Không dùng reset/clean/checkout để loại bỏ công việc chưa commit nếu chưa được cho phép rõ ràng.

## Cấu trúc và cấu hình

- Dùng tên thư mục chữ thường `backend/` và `frontend/` trong code, script và tài liệu.
- Backend: Python/FastAPI; frontend: React/TypeScript/Vite. MongoDB và Google Drive phục vụ lưu trữ theo `README.md`.
- Không commit `.env`, token, khóa riêng, dữ liệu runtime, `.venv`, `node_modules` hoặc artifact build/test. Cập nhật `.env.example` bằng giá trị mẫu khi thêm cấu hình; không thay cấu hình cá nhân nếu nhiệm vụ không yêu cầu.
- Không in bí mật vào log hoặc hội thoại. Xác thực GitHub qua công cụ đã đăng nhập; không yêu cầu người dùng gửi token trong chat.
- Không tự gọi dịch vụ thật hoặc thay đổi dữ liệu MongoDB/Google Drive để kiểm thử khi chưa được giao việc đó.

## Quy ước viết code

Áp dụng mục 17 của `MyHub_README.md` khi viết mới hoặc chỉnh sửa code:

1. Giữ hai thư mục `backend/` và `frontend/`, cùng các file cấu hình cần thiết ở gốc. Mỗi file thêm mới phải được giải thích mục đích. `requirements.txt` nằm trong `backend/`.
2. Chạy backend trong môi trường ảo `venv`; dùng Python và dependencies của môi trường này.
3. Phân lớp backend theo luồng **Controller ↔ DTO ↔ Service ↔ Repository ↔ Database**. Controller tạo DTO Request; Service tạo DTO Response.
4. Lưu biến môi trường backend trong `backend/.env`.
5. Tách `config`, `utils` và các nhóm chức năng khác vào thư mục riêng theo chức năng.
6. Mỗi hàm hoặc đoạn code phải có chú thích bằng **tiếng Việt**, giải thích mục đích và luồng xử lý (flow). Đặt tên biến và hàm bằng **tiếng Anh**.
7. Không gán cứng bí mật trong bất kỳ file nào được push lên GitHub.
8. Local giữ cách chạy thủ công của phiên bản đầu. Người dùng đã yêu cầu CI/CD và tự khởi chạy trên VPS ngày 06/11/2026: production dùng `deploy/` và `.github/workflows/myhub.yml`. Không áp dụng tự khởi chạy production vào máy local.

## Kiểm tra

- Chạy kiểm tra phù hợp với phần thay đổi; không cần chạy lại toàn bộ test khi chỉ sửa tài liệu.
- Backend, từ `backend/`: `.\.venv\Scripts\python.exe -m pytest -q` trên Windows; `.venv/bin/python -m pytest -q` trên Linux.
- Frontend, từ `frontend/`: `npm.cmd run build` trên Windows; `npm run build` trên Linux. Lệnh này kiểm tra TypeScript và build production.
- Khi thay đổi tương tác giao diện, chạy kiểm thử Playwright phù hợp từ `frontend/`: `npm.cmd exec -- playwright test` trên Windows, hoặc `npm exec -- playwright test` trên Linux. Cấu hình dùng Edge và frontend tại `http://localhost:5173`; cần chạy frontend riêng, test không tự khởi động server.
- Test RAR tùy chọn cần `MYHUB_TEST_RAR_PATH`; báo rõ test bị bỏ qua hoặc kiểm tra không chạy được. Không tuyên bố kiểm tra đạt nếu chưa chạy.
- Chạy `git diff --check` trước commit; báo kết quả kiểm tra và hạn chế còn lại khi hoàn tất.
