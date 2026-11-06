# Kết quả kiểm tra MyHub v0.1

## Chuẩn bị VPS/CI/CD và upload chia nhỏ — 06/11/2026

- Backend: **50 passed, 1 skipped** trên Windows/Python 3.13. Test RAR tùy chọn chưa đặt đường dẫn nên skip.
- Frontend TypeScript + production build thành công. **11 kiểm thử Edge đạt**: 10 luồng cũ (upload đổi sang session) và 1 luồng file 104 MiB + 7 byte, có lỗi 503 sau khi server nhận phần đầu; các request đúng 8 MiB và phần cuối 7 byte, không gửi trùng dữ liệu.
- Transport Google giả lập kiểm tra 104 MiB/13 phần, hash dữ liệu, resume sau mất phản hồi và tạo lại UploadService, owner/scope, Content-Length, offset, alignment, session URL/Range, hết hạn, file rỗng và replay sau hoàn tất.
- Thêm bộ cấu hình production trong `deploy/`, hướng dẫn ở `deploy/DEPLOYMENT.md` và workflow GitHub Actions. Kiểm tra Bash syntax cho script bằng Git Bash.
- Actionlint đạt. CI GitHub Actions trên Ubuntu 22.04/Python 3.13.18 đạt backend tests, frontend build và 11 Edge tests tại lượt [42166049473](https://github.com/cdtanhh1807/MyHub/actions/runs/42166049473). Nhãn điều hướng được bổ sung khoảng trống cho font fallback Linux. Deploy bị skip vì đây là PR và chưa bật production.
- Các kiểm thử trên chưa gọi Drive thật, MongoDB thật, tunnel hoặc VPS. Chưa nghiệm thu production, quyền systemd/Nginx, SSH deploy hay rollback thực tế; cần kiểm tra theo hướng dẫn trên VPS trước khi xem CI/CD hoàn tất.
- Ba `.env` cá nhân không được sửa hoặc đưa vào source/artifact. Lần chuyển đầu theo lựa chọn người dùng: dùng Drive root cũ và MongoDB VPS mới, không restore database local.

## Cập nhật 04/11/2026 — tên thư mục và giao diện

- Thư mục thực tế là `backend/` và `frontend/`; đã rà soát mã nguồn, cấu hình mẫu, test, tài liệu và script venv. Không còn tham chiếu tên thư mục viết hoa trong các file dự án được duy trì.
- Ba `.env` cá nhân giữ nguyên từng byte; không có giá trị đang chứa tên thư mục cũ nên không yêu cầu sửa env cho lần đổi tên này.
- Production build và strict TypeScript thành công sau khi đổi thư mục.
- backend: **46 passed, 1 skipped**. Test RAR tùy chọn được skip do lượt chạy này không đặt `MYHUB_TEST_RAR_PATH`; kết quả RAR của lượt 03/11 nằm bên dưới.
- Edge headless: **10 passed** với API giả lập, gồm toàn bộ 6 luồng cũ và 4 kiểm tra mới: chuyển Workspace trực tiếp (Panel mở rộng/thu gọn), dropdown Account bằng bàn phím, Fragment option trong Share, định dạng archive bị vô hiệu hóa.
- Kiểm tra tên cố định **Liam Cao**, cỡ chữ Panel không làm nhãn xuống dòng, dropdown kế thừa góc bo 8/9 px, Escape giữ dialog mở, giao diện dọc/ngang và dark mode.
- Ảnh QA đã cập nhật: [Workspace](data/previews/myhub-workspaces.png), [Account dropdown](data/previews/myhub-account-dropdown.png), [Workspace switcher](data/previews/myhub-workspace-switcher.png), [Mobile dark](data/previews/myhub-mobile-dark.png).

Không gọi OAuth, MongoDB hoặc Google Drive thật trong đợt kiểm tra giao diện này. Các server người dùng đã dừng để đổi tên thư mục; preview do agent mở được dừng sau QA.

## Lượt kiểm tra ban đầu 03/11/2026

Ngày kiểm tra: **03/11/2026**, múi giờ Asia/Saigon.

| Kiểm tra | Kết quả |
|---|---|
| backend pytest | **47 passed** khi chỉ định RAR CLI có sẵn qua `MYHUB_TEST_RAR_PATH` |
| Python dependencies | `pip check`: không có dependency bị lỗi |
| frontend strict TypeScript + production build | `npm run build`: thành công |
| Edge headless | **6 passed**, dùng API giả lập |
| Nội dung archive thật | ZIP/JAR/TAR/GZ/TGZ/ISO tạo và đọc lại đúng; RAR tạo bằng CLI rồi đọc lại `hello.py` đúng byte |
| Cleanup stream | Kiểm tra đóng trước byte đầu, lỗi socket, cancel scope, EOF và dọn tmp/nhả khóa |
| Backup parser | Giữ BSON ObjectId/datetime, chặn tên collection không hợp lệ |

backend chạy trong `backend/.venv` trên Python 3.13.12. frontend build trên Node 22.23.3. Browser tests sử dụng Edge có sẵn, không cài browser mới. RAR test sử dụng công cụ đã có trên máy; không cài hoặc thay cấu hình WinRAR.

Hai cảnh báo deprecation từ Starlette/Authlib về hướng chuyển đổi sang httpx2 vẫn được giữ nguyên trong kết quả test; không làm test thất bại. Bản này khóa httpx 0.28.1 đã kiểm tra tương thích với các đường gọi hiện tại.

Browser đã kiểm tra:

1. Chọn Workspace, mở CodeMirror, sửa và lưu, trạng thái chưa lưu.
2. Xung đột 409 giữ nội dung editor, có thể lưu thành bản sao.
3. Xóa Workspace qua hai bước và nhập chính xác tên.
4. Portrait bottom navigation, Account bottom-sheet, Việt/Anh, dark mode và xoay ngang.
5. Upload hai file dạng raw body, kiểm tra đúng số byte và danh sách được làm mới.
6. pdf.js worker/render text/canvas và zoom PDF trong trình duyệt.

Ảnh QA dùng dữ liệu API giả lập, không phải dữ liệu Drive thật:

- [Workspace desktop](data/previews/myhub-workspaces.png)
- [Files desktop](data/previews/myhub-files.png)
- [Mobile dark mode](data/previews/myhub-mobile-dark.png)

Chưa kiểm chứng tích hợp Google/GitHub OAuth, Drive API và MongoDB thật vì chưa có ba file env cấu hình riêng. Chưa kiểm chứng 7z CLI vì máy chưa có 7-Zip. Chuyển đổi Office, chia sẻ, refresh Drive, backup/restore DB toàn phần và video Range qua Google cần nghiệm thu live theo README sau khi điền cấu hình.

Không khởi tạo/xóa dữ liệu MongoDB, không chỉnh file Drive thật, không triển khai hosting hoặc đưa mã nguồn lên GitHub trong quá trình kiểm tra.
