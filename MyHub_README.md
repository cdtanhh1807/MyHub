# MyHub — Tài liệu tổng hợp yêu cầu dự án

> **Đây KHÔNG phải `README.md` hướng dẫn chạy dự án.** Đây là tài liệu mô tả yêu cầu của dự án. `README.md` thật (các lệnh chạy lần đầu / các lần sau, cách lấy biến môi trường, cách dọn dẹp...) sẽ được viết ở bước viết code.
>
> Quy ước đánh dấu:
> - **[Yêu cầu]** — điều đã xác nhận.
> - **[Đề xuất]** — điều mà AI tự quyết định hoặc AI tự suy ra từ yêu cầu. Tất cả nằm trong mục 19.

---

## 1. Tổng quan dự án

**MyHub** là web-app cá nhân để làm việc liên tục với cùng một bộ file trên nhiều thiết bị (PC, Laptop, Tablet, Smartphone) mà không bị gián đoạn.

**Ý tưởng cốt lõi:**
- Toàn bộ file nằm trên **Google Drive**, trong một folder gốc riêng của dự án. File **không** lưu vào database và không lưu lâu dài trên máy chạy dự án.
- Trong folder gốc, mỗi **Workspace** là một folder con. MyHub là lớp giao diện + backend đứng trên Google Drive: duyệt, tải, upload, chia sẻ, xem trước, chỉnh sửa file.
- **MongoDB** chỉ lưu dữ liệu phụ trợ (thông tin người dùng, phiên đăng nhập, cài đặt, thứ tự Workspace, token Drive đã mã hóa).
- Hệ thống chỉ cho **đúng 2 tài khoản** đăng nhập: Google `cdtanhh@gmail.com` hoặc GitHub `cdtanhh1807`.

---

## 2. Phạm vi của phiên bản đầu tiên

### 2.1. Trong phạm vi

1. Đăng nhập Google / GitHub, chỉ cho phép 2 tài khoản trên.
2. Quản lý **Workspace** (xem/chọn, sắp xếp, tạo, sửa, xóa).
3. Trong Workspace: duyệt file/folder, xem thông tin, download, upload, chia sẻ, tạo folder, đổi tên, xóa.
4. Một số thao tác file: di chuyển/sao chép file giữa các folder trong cùng 1 Workspace hoặc giữa các Workspace (ví dụ: từ một folder của Workspace A sang một folder Workspace B), tải cả folder dạng zip/rar/7z/tar/gz/tgz/jar/iso/..., giao diện khôi phục từ thùng rác, giao diện lịch sử phiên bản.
5. Xem trước / chỉnh sửa theo loại file (bảng ở mục 4.3).
6. Giao diện responsive (PC, tablet, mobile; dọc và ngang), Dark mode, 2 ngôn ngữ (Anh/Việt).
7. Hạ tầng: Docker Compose cho MongoDB, cấu hình bằng `.env`, backup/restore, README hướng dẫn chạy thủ công.

### 2.2. Ngoài phạm vi (chỉ dự tính, **chưa** đưa vào code)

- Hỏi đáp (Q&A) trên một hoặc nhiều tài liệu cùng lúc.
- Tích hợp Gmail: soạn mail, đính kèm file.
- Các chức năng bên trong Workspace ngoài quản lý file: task, remind, checklist...
- Bản app Android.

Sườn code phải **dễ mở rộng** cho các tính năng này (mục 16), nhưng không viết sẵn chức năng.

---

## 3. Workspace

### 3.1. Khái niệm

- **Workspace = một folder nằm trực tiếp trong folder gốc** (`GOOGLE_DRIVE_ROOT_FOLDER_ID`) trên Google Drive.
- **Thư mục hệ thống** (cho backup, file tạm) cũng nằm trong folder gốc nhưng bị **loại khỏi danh sách Workspace và danh sách file**.
- **Nguồn thật sự là Drive**: danh sách Workspace được lấy từ các folder con của folder gốc. MongoDB chỉ lưu những gì Drive không có (thứ tự tự chọn, cài đặt sắp xếp). Nhờ vậy folder bạn tạo trực tiếp trên Drive cũng tự hiện thành Workspace.

### 3.2. Luồng vào hệ thống

1. Đăng nhập thành công.
2. Nếu chưa có Workspace nào được chọn, chuyển tới **màn hình Workspace**: chọn một Workspace có sẵn hoặc tạo mới.
3. Chọn xong mới vào các chức năng file của Workspace đó. Đổi Workspace bất cứ lúc nào qua Panel.

### 3.3. Quản lý Workspace **[Yêu cầu]**

| Chức năng | Mô tả |
|---|---|
| Xem / Chọn | Danh sách Workspace (lưới hoặc danh sách), bấm để vào |
| Sắp xếp | Hai chế độ: **"Sắp xếp"** (theo **tên** hoặc theo **ngày**, tăng/giảm) và **"Tự do"** (**kéo thả** để tự chọn thứ tự) |
| Tạo | Tạo Workspace = tạo folder mới trong folder gốc. Tên không được trùng **[Đề xuất]** |
| Sửa | Đổi tên Workspace = đổi tên folder trên Drive |
| Xóa | Đưa **cả folder cùng toàn bộ file bên trong vào thùng rác Drive**. **Bắt buộc xác nhận hai bước** (ví dụ: hộp thoại cảnh báo nêu rõ số file bị ảnh hưởng, rồi yêu cầu gõ lại tên Workspace) |

Chế độ sắp xếp, chiều sắp xếp và thứ tự kéo thả được lưu trong MongoDB nên **đồng bộ giữa các thiết bị**.

---

## 4. Chức năng cốt lõi trong Workspace

### 4.1. Quản lý file chung (mọi loại file)

| Chức năng | Mô tả |
|---|---|
| Danh sách file | Hiển thị **tên**, **loại file** (đuôi + biểu tượng tương ứng), **dung lượng**, **thời điểm upload**, **thời điểm sửa gần nhất** |
| Duyệt thư mục | Vào/ra các folder con bên trong Workspace; **breadcrumb**; chuyển chế độ **danh sách/lưới**; **tìm kiếm** và **sắp xếp** cơ bản (tên, loại, dung lượng, ngày upload, ngày sửa; tăng/giảm; folder luôn lên trước) |
| Download | Tải file về thiết bị. backend stream trực tiếp, không giữ file trên đĩa |
| Upload | Upload một hoặc nhiều file (chọn hoặc kéo thả), có thanh tiến trình, vào đúng folder đang xem |
| Tạo folder | Tạo folder con trong thư mục đang xem |
| Đổi tên | Đổi tên file/folder |
| Xóa | Đưa vào **thùng rác Drive** (khôi phục được trong Drive trong thời hạn Drive giữ) |
| Phạm vi truy cập | Mọi thao tác **chỉ trong cây thư mục của `GOOGLE_DRIVE_ROOT_FOLDER_ID`**; ngoài ra mọi thao tác file còn bị giới hạn trong **Workspace đang chọn**. backend kiểm tra chuỗi thư mục cha của mọi file/folder được yêu cầu và **chặn nếu nằm ngoài phạm vi** |

Lưu ý: file dạng Google gốc (Docs/Sheets/Slides) **không có đuôi file và không có dung lượng** trên Drive, nên giao diện nhận diện bằng mimeType và hiển thị "—" ở cột dung lượng.

### 4.2. Chia sẻ (Share) **[Yêu cầu]**

Mục tiêu: chia sẻ đủ các chế độ của Google Drive **ngay trong MyHub**, không cần mở Drive. Áp dụng cho cả file và folder.

| Chế độ | Mô tả |
|---|---|
| Hạn chế (Restricted) | Chỉ những người được thêm mới truy cập được |
| Mời theo email | Thêm email với vai trò **Viewer / Commenter / Editor**; tùy chọn gửi email thông báo |
| Anyone with the link | Bật/tắt; chọn vai trò **Viewer / Commenter / Editor** |
| Sao chép link | Nút sao chép link Google Drive của file |
| Trạng thái hiện tại | Hiển thị trực quan: biểu tượng khóa (hạn chế) hoặc quả cầu/link (ai có link), số người được chia sẻ ngay trên danh sách file; trong hộp thoại Share liệt kê từng người và vai trò, cho **đổi vai trò / gỡ quyền** **[Đề xuất]** |
| Cảnh báo | Khi chọn "Anyone with the link" + Editor thì hiện cảnh báo rủi ro **[Đề xuất]** |

Link được chia sẻ là **link của Google Drive** (không phải link MyHub), nên người nhận mở bằng giao diện của Google.

### 4.3. Ma trận xử lý theo loại file **[Yêu cầu]**

| Nhóm | Định dạng | Hành vi | Cách xử lý |
|---|---|---|---|
| Google Docs / Sheets (gốc Google) | `docs`, `sheets` (và Slides gốc **[Đề xuất]**) | **Xem trong app** + nút **"Chỉnh sửa trong Google Docs/Sheets"** mở **tab mới** | Nhúng trang `/preview` của Google trong iframe; nút mở link chỉnh sửa của Google ở tab mới |
| Văn bản Office | `docx` | **Chỉ xem**, **giữ nguyên định dạng** | Office → PDF qua Drive → PDF viewer |
| Bảng tính Office | `xlsx`, `xls` | **Chỉ xem**, giữ nguyên định dạng | **Thử** pipeline PDF trước. Nếu bị chia trang xấu → chuyển sang `/preview` của Drive. Quy tắc này cấu hình **theo từng loại file** để đổi dễ |
| Trình chiếu | `pptx`, `ppt` | **Xem** rõ ràng | Office → PDF qua Drive → PDF viewer |
| PDF | `pdf` | **Xem** rõ ràng | PDF viewer trong app (zoom, chuyển trang) |
| Hình ảnh | `jpg`, `png`, `gif`, `webp`, `svg`... | **Xem** rõ ràng | Image viewer (zoom, lướt qua lại giữa các ảnh) |
| Video | `mp4`, `webm`, `mov`... | **Xem** rõ ràng | Trình phát HTML5; backend stream hỗ trợ tua (HTTP Range) |
| Text | `txt`, `md`, `csv`, `json`, `log`, `yaml`... | **Xem và sửa** | **CodeMirror 6** |
| Code | `.py`, `.js`, `.ts`, `.java`, `.html`, `.css`, `.sql`... | **Xem và sửa** | **CodeMirror 6** (tô màu cú pháp theo ngôn ngữ) |
| Còn lại | `zip`, `rar`, `7z`... | Chỉ xem **metadata** | Màn hình thông tin file + nút download/share |

### 4.4. Chi tiết các luồng xử lý quan trọng

**a) Xem Google Docs/Sheets bằng `/preview`**
- Trang `/preview` là cách nhúng được Google hỗ trợ; trang `/edit` thì không nhúng ổn định nên chỉ mở bằng tab mới.
- Điều kiện: trình duyệt phải đang đăng nhập Google bằng tài khoản có quyền. Nếu chưa, giao diện hiện hướng dẫn kèm nút mở Google ở tab mới. **[Đề xuất]**

**b) Office → PDF qua Drive**
1. Service kiểm tra file nằm trong Workspace và loại file được hỗ trợ; kiểm tra cache PDF (khóa theo ID file + phiên bản nội dung).
2. Nếu chưa có cache: backend tạo một **bản sao tạm** của file, chuyển đổi sang định dạng Google, đặt trong thư mục hệ thống.
3. Xuất bản sao đó ra PDF (export), rồi **xóa vĩnh viễn bản sao tạm**.
4. backend stream PDF về trình duyệt; PDF viewer hiển thị. PDF có thể được cache trong `data/cache` với giới hạn dung lượng cấu hình được. **[Đề xuất]**
5. **File vượt giới hạn export của Drive hoặc chuyển đổi lỗi** → tự chuyển sang `/preview` của Drive; nếu vẫn không được thì chỉ hiện metadata + nút download. **[Đề xuất]**

**c) "Lưu" file code/text lên Drive — không phải xóa file cũ rồi tạo file mới**
- backend gọi thao tác cập nhật nội dung (`files.update`) lên **chính file đó**: giữ nguyên ID, tên, vị trí, link chia sẻ. Drive tạo một revision mới; các revision cũ không ghim chỉ được Drive giữ trong thời gian ngắn, nên đó **không phải kênh sao lưu lâu dài**.
- **Chống ghi đè nhầm khi dùng nhiều thiết bị**: khi mở file, frontend nhận kèm "phiên bản hiện tại". Khi lưu, Service so sánh với phiên bản đang có trên Drive. Nếu đã bị thiết bị khác sửa → trả lỗi xung đột và giao diện cho chọn: ghi đè / tải lại / lưu thành bản sao. **[Đề xuất]**
- File quá lớn (mặc định **5 MB**, cấu hình được) hoặc file nhị phân → chỉ cho xem/tải, không mở bằng editor, để tránh treo trình duyệt. **[Đề xuất]**

**d) Stream file lớn**
- Upload, download, video, PDF đều **stream** qua backend, không đọc cả file vào RAM, không lưu lâu dài trên đĩa.

---

## 5. Xác thực & truy cập Drive

### 5.1. Đăng nhập **[Yêu cầu]**

- Chỉ có 2 cách: **Google** (email `cdtanhh@gmail.com`) hoặc **GitHub** (username `cdtanhh1807`). Mọi tài khoản khác bị từ chối.
- Với Google: chấp nhận khi email khớp và đã được Google xác minh. Với GitHub: **chỉ kiểm tra username** (không kiểm tra user ID số).
- Luồng: OAuth 2.0 Authorization Code ở backend → đối chiếu whitelist trong `.env` → cấp JWT (access token ngắn hạn + refresh token) → frontend gọi API. Refresh token đặt trong cookie `httpOnly` cho web; API cũng hỗ trợ Bearer token để sau này dùng cho app Android. **[Đề xuất]**
- Panel hiển thị: avatar + tên + (Gmail nếu đăng nhập Google / username nếu đăng nhập GitHub) + nút Đăng xuất.

### 5.2. Truy cập Drive: đăng nhập GitHub vẫn dùng được Google Drive **[Yêu cầu]**

1. "Đăng nhập vào MyHub" và "cấp quyền Drive cho backend" là **hai việc tách riêng**.
2. backend dùng **một refresh token Drive của chủ tài khoản `cdtanhh@gmail.com`**, cấp **một lần**, **lưu mã hóa trong MongoDB** (chọn MongoDB thay vì `.env`, lý do ở mục 19), dùng cho mọi request Drive dù bạn đăng nhập bằng Google hay GitHub.
3. Bước cấp quyền một lần chỉ cho phép khi đã đăng nhập vào MyHub, và chỉ chấp nhận nếu tài khoản Google vừa cấp quyền **đúng là** `cdtanhh@gmail.com`.
4. Scope Drive: `https://www.googleapis.com/auth/drive`. Không dùng được `drive.file` vì scope đó không thấy folder bạn tạo tay.
5. Không dùng Service Account (có dung lượng riêng, không dùng được 400GB của bạn).
6. **OAuth consent screen phải chuyển sang "In production"**, nếu để "Testing" thì refresh token chỉ sống khoảng 7 ngày. Dùng cá nhân được; sẽ có cảnh báo "app chưa xác minh" và bạn bấm tiếp tục. **README sẽ ghi rõ bước này.**

---

## 6. Công nghệ

### 6.1. Bạn đã chọn **[Yêu cầu]**

| Lớp | Công nghệ |
|---|---|
| backend | **FastAPI** (Python), chạy trong **venv** |
| frontend | **React + TypeScript** |
| Database | **MongoDB** (Docker) |
| Lưu file | **Google Drive** (không lưu file vào DB) |
| Hạ tầng | **Docker Compose** (Docker Engine trong WSL2) |
| Editor code/text | **CodeMirror 6** |

### 6.2. Bổ sung AI đề xuất **[Đề xuất]**

| Mục đích | Công nghệ | Lý do |
|---|---|---|
| Build frontend | **Vite** | Nhanh, nhẹ |
| UI | **Tailwind CSS** + component nền | Dễ responsive, Dark mode, tông xanh/trắng/xám |
| Routing / gọi API | React Router, TanStack Query, Axios | Cache, trạng thái loading/lỗi gọn |
| State nhẹ | Zustand | Lưu theme, ngôn ngữ, Workspace đang chọn, trạng thái Panel |
| Đa ngôn ngữ | i18next | Anh/Việt |
| Kéo thả sắp xếp Workspace | dnd-kit | Hỗ trợ cảm ứng tốt |
| Xem PDF | pdf.js (react-pdf) | Dùng chung cho PDF, pptx, docx |
| backend | Pydantic v2, pydantic-settings, PyMongo (async API), httpx, Authlib, PyJWT, cryptography, google-auth | Gọi Drive REST bằng httpx để stream file lớn |
| Phiên bản | Python 3.12, Node.js LTS, MongoDB bản cố định (ví dụ `mongo:7.0`) | Không dùng `latest` để môi trường tái lập được. Phiên bản chính xác sẽ xác minh và chốt khi viết code |

Không còn cần Monaco, docx-preview, SheetJS vì docx/xlsx/xls chỉ xem qua PDF hoặc `/preview`.

---

## 7. Kiến trúc backend

**[Yêu cầu]** Phân lớp `Controller ↔ DTO Request/Response ↔ Service ↔ Repository ↔ Database`, với quy tắc bạn đã chốt: **DTO Request do Controller tạo rồi truyền xuống Service; DTO Response do Service tạo rồi trả lên Controller.**

```
HTTP Request ──► Controller ──(tạo)──► DTO Request ──► Service ──► Repository ──► MongoDB
                                                         │                   └──► Google Drive
HTTP Response ◄── Controller ◄──────── DTO Response ◄───┘   (Service tạo DTO Response)
```

| Lớp | Trách nhiệm | Không được làm |
|---|---|---|
| Controller | Nhận HTTP, lấy dữ liệu từ path/query/body/người dùng hiện tại, **tạo DTO Request**, gọi Service, nhận **DTO Response** và trả về HTTP | Chứa nghiệp vụ, truy cập DB/Drive trực tiếp |
| DTO Request / Response | Định nghĩa và validate dữ liệu vào/ra | Chứa logic |
| Service | Toàn bộ nghiệp vụ (kiểm tra phạm vi Workspace, chuyển đổi PDF, kiểm tra xung đột khi lưu...), điều phối Repository, **tạo DTO Response** | Biết chi tiết HTTP, cú pháp truy vấn |
| Repository | Truy cập dữ liệu (MongoDB **và** Google Drive), trả về model dữ liệu thô, **không trả DTO** | Chứa nghiệp vụ |

Với các phản hồi dạng stream (download, video, PDF), DTO Response chứa luồng dữ liệu và thông tin header; Controller bọc lại thành phản hồi streaming.

Google Drive được coi là **một nguồn dữ liệu ngang hàng với MongoDB**, nên có `DriveRepository`. Sau này đổi hoặc thêm nơi lưu trữ không ảnh hưởng tầng Service.

### 7.1. Các nhóm API dự kiến **[Đề xuất]**

| Nhóm | Việc chính |
|---|---|
| `auth` | Đăng nhập Google/GitHub, refresh token, đăng xuất, thông tin người dùng hiện tại |
| `drive-connection` | Cấp quyền Drive một lần, kiểm tra tình trạng kết nối |
| `workspaces` | Liệt kê, tạo, đổi tên, xóa, lưu thứ tự kéo thả |
| `files` | Liệt kê, tìm, tạo folder, đổi tên, xóa, upload, download, stream |
| `preview` | PDF chuyển đổi, nội dung text cho editor, lưu nội dung có kiểm tra xung đột |
| `sharing` | Xem/thêm/đổi/gỡ quyền, bật/tắt link |
| `settings` | Ngôn ngữ, theme, chế độ sắp xếp, kiểu hiển thị |

### 7.2. MongoDB lưu gì **[Đề xuất, tối giản]**

| Collection | Nội dung |
|---|---|
| `users` | Hồ sơ người dùng (nhà cung cấp đăng nhập, tên, avatar, email/username, lần đăng nhập cuối) |
| `user_settings` | Ngôn ngữ, theme, chế độ/chiều sắp xếp Workspace, kiểu hiển thị danh sách/lưới |
| `workspace_orders` | Thứ tự kéo thả của Workspace (khóa theo ID folder trên Drive) |
| `drive_credentials` | Refresh token Drive **đã mã hóa**, email tài khoản cấp quyền |
| `refresh_sessions` | Phiên đăng nhập (chỉ lưu bản băm), có tự hết hạn (TTL) |
| `system_state` | ID thư mục hệ thống trên Drive và các giá trị hệ thống khác |

Dữ liệu suy ra được từ Drive (danh sách Workspace, danh sách file) **không phải nguồn sự thật** trong MongoDB.

---

## 8. Kiến trúc frontend

- Tách rõ: **giao diện (components/pages)** ↔ **logic theo tính năng (features)** ↔ **lớp gọi API (services)**. Mọi lệnh gọi API đi qua một lớp duy nhất để sau này đóng gói Android không phải sửa nghiệp vụ.
- **AppShell** gồm Panel + vùng nội dung; Panel tự đổi dạng theo hướng màn hình.
- Mỗi loại file có một **viewer/editor riêng**, đăng ký trong **một bảng ánh xạ `loại file → component`** (kèm quy tắc mục 4.3, ví dụ xlsx → PDF hay `/preview`). Thêm loại file mới chỉ cần thêm một dòng.
- Lúc dev, Vite chuyển tiếp (proxy) `/api` sang backend để tránh vướng CORS. **[Đề xuất]**

### Các màn hình chính

| Màn hình | Nội dung |
|---|---|
| Đăng nhập | Hai nút Google / GitHub |
| Workspace | Danh sách Workspace, sắp xếp, tạo/sửa/xóa |
| Files | Danh sách file trong Workspace, breadcrumb, tìm kiếm, upload |
| Viewer/Editor | Mở một file theo loại (mục 4.3) |
| Cài đặt (trong Account) | Ngôn ngữ, theme |

---

## 9. Giao diện (UI/UX) **[Yêu cầu]**

| Hạng mục | Yêu cầu |
|---|---|
| Màu chủ đạo | Xanh dương, trắng, xám |
| Responsive | Tự thích ứng PC, Tablet, Mobile; cả chiều **dọc** và **ngang** |
| Dark mode | Có (3 chế độ: Sáng / Tối / Theo hệ thống) |
| Ngôn ngữ | Tiếng Anh và Tiếng Việt, đổi được trong giao diện |
| Giao diện **ngang** | Panel nằm **bên trái**, **mở rộng/thu gọn** được. **Dưới cùng Panel**: thông tin account (avatar, tên, Gmail hoặc username GitHub) + nút **Đăng xuất** |
| Giao diện **dọc** | Panel chuyển **xuống đáy màn hình**: thanh điều hướng dưới gồm các mục chính (Workspaces, Files, ... và một mục **Account**). Bấm Account mở **bottom-sheet** chứa avatar, tên, Gmail/username, đổi ngôn ngữ, đổi theme và nút **Đăng xuất** |
| Panel mở rộng được | Panel thiết kế là **danh sách mục có thể thêm sau** ("Chat với tài liệu", "Mail", "Task"...) mà không phải thiết kế lại bố cục |
| Workspace đang chọn | Hiển thị tên Workspace hiện tại ở đầu Panel / thanh tiêu đề, bấm để đổi nhanh |

---

## 10. Cấu trúc thư mục dự kiến

Cấu trúc **trong thư mục dự án** (nằm trên ổ Windows):

```
MyHub/
├── backend/
│   ├── .env                    # biến môi trường backend (KHÔNG push)
│   ├── .env.example            # mẫu, không chứa bí mật (push được)
│   ├── .venv/                  # môi trường ảo Python (KHÔNG push)
│   ├── requirements.txt        # thư viện Python
│   ├── scripts/                # backup_db.py, restore_db.py (chạy trong venv)
│   └── app/
│       ├── main.py             # điểm khởi động FastAPI
│       ├── controllers/        # Controller (router)
│       ├── dtos/               # DTO Request / DTO Response
│       ├── services/           # Service
│       ├── repositories/       # Repository (MongoDB + Google Drive)
│       ├── models/             # Mô hình document MongoDB
│       ├── config/             # Đọc & validate biến môi trường
│       ├── core/               # Bảo mật, JWT, dependency, exception handler
│       └── utils/              # Hàm tiện ích dùng chung
├── frontend/
│   ├── .env                    # chỉ giá trị công khai (KHÔNG push)
│   ├── .env.example
│   ├── .npmrc                  # đưa cache npm vào trong dự án
│   └── src/
│       ├── app/  pages/  features/  components/
│       ├── services/           # lớp gọi API
│       ├── hooks/  store/  i18n/  theme/  types/  utils/
├── docker/
│   └── mongo-init/             # script tạo user riêng cho app khi MongoDB khởi tạo lần đầu
├── data/                       # dữ liệu runtime của backend (KHÔNG push, trừ .gitkeep)
│   ├── cache/                  # cache PDF đã chuyển đổi (có giới hạn dung lượng)
│   ├── tmp/                    # file tạm
│   └── backups/                # bản sao lưu DB tạo ra
├── scripts/
│   └── cleanup.sh              # dọn container, image, thư mục dữ liệu MongoDB (chạy trong WSL2/Ubuntu)
├── .env                        # biến cho docker-compose (KHÔNG push)
├── .env.example
├── .gitignore
├── .gitattributes              # ép xuống dòng LF cho mọi máy
├── docker-compose.yml
├── README.md                   # hướng dẫn chạy (viết ở bước code)
└── MyHub_README.md             # tài liệu này
```

Dữ liệu MongoDB **không nằm trong cây thư mục này**, mà nằm ở thư mục trong WSL2 (mục 11).

**Các file phụ và mục đích:**

| File | Mục đích |
|---|---|
| `*.env.example` | Bản mẫu có tên biến nhưng không có giá trị thật, push lên GitHub để máy mới biết cần điền gì |
| `.gitattributes` | Máy Windows tạo file xuống dòng kiểu CRLF sẽ làm hỏng script chạy trên Ubuntu/WSL2; file này ép LF |
| `docker/mongo-init/` | Tạo user riêng cho app (quyền hạn chế) thay vì để backend dùng tài khoản root của MongoDB |
| `frontend/.npmrc` | Đưa cache npm vào `frontend/.npm-cache` để xóa dự án là sạch |
| `data/.gitkeep` | Giữ thư mục `data/` trên Git nhưng không đẩy dữ liệu |
| `backend/scripts/backup_db.py`, `restore_db.py` | Sao lưu/khôi phục MongoDB (mục 14) |
| `scripts/cleanup.sh` | Gỡ sạch phần nằm ngoài thư mục dự án (mục 13) |

---

## 11. Docker & MongoDB (Docker Engine trong WSL2) **[Yêu cầu]**

- Chỉ **MongoDB** chạy bằng container ở v1. backend và frontend bạn chạy thủ công trên Windows.
- Lệnh `docker compose` chạy **trong terminal WSL2**, tại thư mục dự án (ổ Windows truy cập được từ WSL2 qua `/mnt/<ổ đĩa>/...`).
- `docker-compose.yml` **không chứa bí mật**: mọi giá trị nhạy cảm đọc từ **`.env` ở thư mục gốc** (nằm trong `.gitignore`).
- backend trên Windows kết nối `localhost:27017`; port chỉ mở ở `127.0.0.1` (không lộ ra mạng). Windows truy cập được nhờ cơ chế chuyển tiếp localhost của WSL2; nếu máy bạn không chạy được, README sẽ có cách xử lý.

### 11.1. Vị trí dữ liệu MongoDB

**Vấn đề:** thư mục dự án nằm trên ổ Windows. Gắn thư mục Windows vào container MongoDB thường gây lỗi quyền hoặc chậm, nên **không dùng cách đó**.

**Cách chọn [Đề xuất]:** gắn (bind mount) vào **một thư mục cố định trong chính WSL2** (ổ ext4), do bạn đặt đường dẫn trong biến `MONGO_DATA_DIR` của `.env` gốc. Ví dụ: `/home/<tên-user-wsl>/myhub-data/mongodb`.

Lý do: nằm ở **một vị trí rõ ràng, bạn nhìn và kiểm soát được**; giữ được hiệu năng và độ an toàn dữ liệu của MongoDB; trên Ubuntu khi deploy dùng y hệt cách này.

### 11.2. Các thông tin sẽ nêu rõ trong README

| Hạng mục | Nội dung |
|---|---|
| Image & phiên bản | Tên image + tag cố định (không `latest`) |
| Tên container | Tên cố định, dễ nhận biết |
| Tài khoản | Root và tài khoản riêng cho app, đều lấy từ `.env` gốc; cách tạo mật khẩu mạnh |
| Port | `127.0.0.1:27017` |
| **Volume** | Bind mount `MONGO_DATA_DIR` (thư mục trong WSL2, mục 11.1); bên trong container là `/data/db` |
| Giới hạn tài nguyên | Giới hạn RAM và cache của MongoDB |
| Log | Giới hạn kích thước log container (log do Docker lưu, nên phải giới hạn và nêu vị trí) |
| Khởi động | Không tự khởi động lại (`restart: "no"`) vì bạn muốn tự chạy thủ công **[Đề xuất]** |

---

## 12. Biến môi trường & bảo mật **[Yêu cầu]**

### 12.1. Các file env và thuộc phần nào của README

| File | Thuộc phần README | Dùng cho | Push GitHub? |
|---|---|---|---|
| `/.env` (gốc) | **Hạ tầng / Docker** | `docker-compose.yml`: tài khoản MongoDB, port, `MONGO_DATA_DIR` | ❌ |
| `/backend/.env` | **backend** | FastAPI: OAuth, JWT, mã hóa, kết nối Mongo, Drive, đường dẫn dữ liệu cục bộ | ❌ |
| `/frontend/.env` | **frontend** | URL API (chỉ giá trị công khai, **tuyệt đối không để bí mật** vì sẽ lộ trong bundle) | ❌ |
| `*.env.example` | Cả ba | Bản mẫu không bí mật | ✅ |

### 12.2. Biến của `/.env` (gốc)

| Biến | Ý nghĩa | Cách lấy |
|---|---|---|
| `MONGO_ROOT_USERNAME`, `MONGO_ROOT_PASSWORD` | Tài khoản root của MongoDB | Tự đặt; mật khẩu sinh bằng `openssl rand -base64 32` |
| `MONGO_APP_USERNAME`, `MONGO_APP_PASSWORD`, `MONGO_DB_NAME` | Tài khoản riêng và tên DB cho app | Tự đặt |
| `MONGO_PORT` | Port mở ở `127.0.0.1` | Mặc định `27017` |
| `MONGO_DATA_DIR` | Đường dẫn thư mục dữ liệu MongoDB **trong WSL2** | Tự chọn, ví dụ `/home/<user>/myhub-data/mongodb` |

### 12.3. Biến của `/backend/.env`

| Biến | Ý nghĩa | Cách lấy |
|---|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | OAuth Google | **Bạn đã có** (Cloud Console, project MyHub, APIs & Services, Credentials) |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | ID folder gốc trên Drive | **Bạn đã có** (phần cuối URL khi mở folder trên Drive) |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | OAuth GitHub | **Chưa có.** Tạo ở GitHub: Settings, Developer settings, OAuth Apps, New OAuth App; README nêu rõ Callback URL |
| `ALLOWED_GOOGLE_EMAIL` | `cdtanhh@gmail.com` | Cố định |
| `ALLOWED_GITHUB_USERNAME` | `cdtanhh1807` | Cố định |
| `MONGODB_URI` | Chuỗi kết nối MongoDB | Ghép từ `MONGO_APP_*` trong `/.env` gốc (hai file phải khớp nhau) |
| `JWT_SECRET_KEY` | Khóa ký JWT | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ENCRYPTION_KEY` | Khóa mã hóa refresh token Drive | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `DRIVE_SYSTEM_FOLDER_NAME` | Tên thư mục hệ thống trên Drive | Giá trị mặc định có sẵn |
| `LOCAL_DATA_DIR` | Thư mục `data/` của dự án | Mặc định `../data` |
| `MAX_EDIT_FILE_SIZE_MB`, `PDF_CACHE_MAX_MB` | Giới hạn editor, giới hạn cache PDF | Mặc định `5`, và một giá trị hợp lý |
| `BACKEND_URL`, `FRONTEND_URL`, `CORS_ORIGINS` | Địa chỉ các thành phần | Điền theo cách bạn chạy |
| `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` | Thời hạn phiên | Mặc định có sẵn |

**Redirect URI cần đăng ký** (Google Cloud Console cho đăng nhập Google và cấp quyền Drive; GitHub OAuth App cho đăng nhập GitHub): dạng `http://localhost:8000/api/v1/...`. Khi deploy lên tên miền HTTPS thật, phải **đăng ký thêm** các redirect URI theo tên miền đó.

### 12.4. Biến của `/frontend/.env`

`VITE_API_BASE_URL` (địa chỉ API). Chỉ chứa giá trị công khai.

README sẽ nêu **cách lấy từng giá trị** và **lệnh sinh sẵn** cho mọi biến cần chuỗi mã hóa.

---

## 13. Dung lượng & dọn dẹp **[Yêu cầu]**

Mục tiêu: biết chính xác dự án chiếm chỗ nào; khi gỡ thì **sạch hoàn toàn**.

| Thành phần | Nằm ở đâu | Cách dọn |
|---|---|---|
| Source code | Thư mục dự án (Windows) | Xóa thư mục dự án |
| venv Python | `backend/.venv` | Nằm trong thư mục dự án → xóa cùng |
| Cache pip | Không có | Lệnh cài dùng `--no-cache-dir` nên **không tạo cache** |
| `node_modules` | `frontend/node_modules` | Xóa cùng thư mục dự án |
| Cache npm | `frontend/.npm-cache` (nhờ `.npmrc`) | Xóa cùng thư mục dự án |
| Bản build, cache Vite | `frontend/dist`, `node_modules/.vite` | Xóa cùng thư mục dự án |
| Cache PDF, file tạm, bản backup cục bộ | `data/` | Xóa cùng thư mục dự án |
| **Dữ liệu MongoDB** | `MONGO_DATA_DIR` trong **WSL2** (ngoài thư mục dự án) | `scripts/cleanup.sh` xóa; hoặc xóa tay sau khi `docker compose down` |
| **Image Docker** (`mongo`) | Kho của Docker Engine trong WSL2 | `docker compose down --rmi all` (nằm trong `cleanup.sh`) |
| **Container, log container, network** | Docker Engine trong WSL2 | `docker compose down` |
| Python, Node.js, WSL2, Docker Engine | Cài trên hệ thống | Điều kiện tiên quyết, gỡ như phần mềm thường |
| Dữ liệu trình duyệt (theme, ngôn ngữ, phiên) | Trình duyệt | Xóa dữ liệu trang |
| File của bạn trên Drive | Google Drive | **Không bị ảnh hưởng** khi gỡ dự án khỏi máy |

**Quy trình gỡ sạch (README sẽ ghi từng lệnh):**
1. Dừng backend và frontend.
2. Trong WSL2: chạy `scripts/cleanup.sh` (hạ container + xóa image + xóa thư mục `MONGO_DATA_DIR`).
3. Xóa thư mục dự án trên Windows.
4. Tùy chọn: ổ đĩa ảo của WSL2 có thể **không tự thu nhỏ** sau khi xóa dữ liệu bên trong; README sẽ hướng dẫn thu gọn nếu bạn muốn lấy lại dung lượng trên Windows.

**Tổng kết các vị trí trên máy:** (1) thư mục dự án trên Windows, (2) thư mục `MONGO_DATA_DIR` và kho Docker trong WSL2. Ngoài hai nơi này **không có gì khác** (cache pip/npm đã được loại bỏ hoặc đưa vào dự án).

---

## 14. Backup, chuyển máy **[Yêu cầu]**

Điều kiện: máy mới chỉ cần `git pull` rồi làm theo các bước trong README là có lại **code + dữ liệu**.

| Thứ cần chuyển | Đi qua đâu | Ghi chú |
|---|---|---|
| Source code | **GitHub** | Dùng **repo private** **[Đề xuất]** |
| File của bạn | **Google Drive** | Không cần chuyển |
| Dữ liệu MongoDB | **Backup lên Drive** | `backup_db.py` xuất toàn bộ collection ra một file nén, lưu bản cục bộ ở `data/backups` **và** tải lên thư mục hệ thống trên Drive. `restore_db.py` nạp lại (từ Drive hoặc từ file cục bộ). Viết bằng Python để chạy giống nhau trên Windows và Ubuntu, không cần công cụ `mongodump` **[Đề xuất]** |
| File bí mật (`.env` x3) | **Thủ công, an toàn** | Cố ý không nằm trên GitHub nên máy mới phải **tạo lại**. Bạn nên cất giá trị gốc trong trình quản lý mật khẩu |

**Các bước tổng quát trên máy mới (README sẽ ghi lệnh cụ thể):**
1. `git clone` dự án.
2. Tạo lại 3 file `.env` từ `.env.example` với giá trị cũ. **Giữ nguyên `ENCRYPTION_KEY`**, nếu đổi thì token Drive đã lưu không giải mã được (khi đó chỉ cần cấp quyền Drive lại, không mất file).
3. Tạo thư mục `MONGO_DATA_DIR`, chạy `docker compose up -d`.
4. Tạo venv, cài `requirements.txt`, chạy backend; cài và chạy frontend.
5. Đăng nhập, cấp quyền Drive một lần.
6. Chạy `restore_db.py` lấy bản backup mới nhất từ Drive. Mặc định **không ghi đè** collection `drive_credentials` để giữ token vừa cấp. **[Đề xuất]**

Dữ liệu MongoDB được thiết kế **tối giản và tái tạo được** (mục 7.2), nên mất DB cũng không mất file.

---

## 15. Môi trường dev (Windows + WSL2) và deploy (Ubuntu) **[Yêu cầu]**

| Giai đoạn | Cách chạy |
|---|---|
| **Dev** | backend và frontend chạy **trực tiếp trên Windows**; MongoDB chạy bằng Docker Engine **trong WSL2**; test giao diện mobile bằng **DevTools của trình duyệt** |
| **Sau khi hoàn thiện** | **Deploy** hệ thống, truy cập bằng điện thoại qua web |
| **Sau khi ổn định** | Build **app Android** |

Để "pull về Ubuntu, setup môi trường là chạy được", sườn code tuân thủ:
- Không gán cứng đường dẫn Windows; dùng đường dẫn tương đối hoặc cấu hình qua env, xử lý bằng `pathlib`.
- `.gitattributes` ép LF; script dùng `.sh` (chạy trong WSL2/Ubuntu) hoặc Python (chạy mọi nơi).
- Mọi địa chỉ (backend, frontend, CORS, cookie, redirect OAuth) cấu hình qua env để đổi sang tên miền HTTPS khi deploy.
- README ghi lệnh **cho cả Windows (PowerShell) lẫn Ubuntu** và nói rõ lệnh nào chạy ở đâu (Windows hay WSL2).

Cách deploy cụ thể (tên miền, reverse proxy, chạy backend như dịch vụ...) **chưa nằm trong v1** và sẽ làm sau; thiết kế hiện tại không cản trở việc đó.

---

## 16. Khả năng mở rộng & Android

**Nguyên tắc để mở rộng sau này (chưa code tính năng):**

1. **Mọi thứ tham chiếu file bằng `drive_file_id`, và mọi thứ thuộc Workspace tham chiếu bằng `workspace_id` (= ID folder trên Drive).** Q&A tài liệu, đính kèm Gmail, task/remind/checklist trong Workspace chỉ cần lưu hai ID này (trong MongoDB), không sao chép file.
2. **Chia module theo tính năng** ở cả backend và frontend (hiện là `auth`, `workspaces`, `files`, `sharing`...). Thêm module mới theo đúng khuôn Controller/DTO/Service/Repository, không sửa lõi.
3. **Lớp Drive tách riêng** để tính năng mới (ví dụ đọc nội dung file cho Q&A) tái sử dụng được.
4. **Xin quyền Google theo từng bước:** hiện chỉ xin scope Drive; thêm Gmail sau thì xin thêm scope, không làm lại hệ thống đăng nhập.
5. **Panel là danh sách mục mở rộng được** (mục 9).

**Hướng tới Android [Đề xuất]:** biến web-app thành **PWA**, rồi dùng **Capacitor** đóng gói chính code React thành app Android. Đã chuẩn bị sẵn: lớp `services` tách riêng, API hỗ trợ Bearer token, địa chỉ backend cấu hình qua env. Phần cần xử lý riêng khi làm bản Android: luồng OAuth trong app (deep link / trình duyệt hệ thống).

---

## 17. Quy ước viết code phiên bản đầu **[Yêu cầu]**

1. Dự án gồm 2 thư mục **backend** và **frontend**, cùng các file ở gốc (`.gitignore`, `docker-compose.yml`...) và các file cần thiết khác (mỗi file thêm đều được giải thích mục đích). **`requirements.txt` nằm trong `backend/`.**
2. backend chạy **trong venv**.
3. backend phân lớp **Controller ↔ DTO ↔ Service ↔ Repository ↔ Database**, với DTO Request do Controller tạo và DTO Response do Service tạo.
4. Biến môi trường backend lưu trong **`.env` trong thư mục backend**.
5. `config`, `utils`... nằm trong **thư mục riêng** theo chức năng.
6. **Mỗi hàm / đoạn code có chú thích mục đích và luồng đi (flow)**, viết bằng **tiếng Việt**; tên biến/hàm bằng **tiếng Anh**.
7. Không gán cứng bí mật ở bất kỳ file nào được push lên GitHub.
8. Phiên bản này **không tự động hóa việc chạy**: bạn tự tạo/start container, tự chạy backend, tự chạy frontend.

---

## 18. Nội dung `README.md` (hướng dẫn chạy) sẽ viết kèm khi code

- Yêu cầu cài đặt trước (Python, Node.js, WSL2 + Docker Engine).
- Cách lấy/tạo từng giá trị trong các file `.env`, kèm lệnh sinh khóa; nói rõ mỗi `.env` thuộc phần nào.
- Cách đặt OAuth consent screen sang **In production** và đăng ký redirect URI.
- Lệnh **chạy lần đầu**: tạo `.env` → tạo thư mục `MONGO_DATA_DIR` → tạo & start container MongoDB (WSL2) → tạo venv, cài `requirements` (Windows) → chạy backend → cài & chạy frontend → đăng nhập và cấp quyền Drive lần đầu.
- Lệnh **chạy những lần sau**: start lại container → kích hoạt venv chạy backend → chạy frontend.
- Backup/restore, chuyển máy, **gỡ sạch** dự án, thu gọn ổ đĩa WSL2.
- Bảng "dự án dùng dung lượng ở đâu" (mục 13).
- Lệnh cho **cả Windows lẫn Ubuntu**, ghi rõ chạy ở đâu.

---

## 19. Các điểm AI tự chốt

| # | Điểm | AI chọn | Lý do |
|---|---|---|---|
| 1 | Google Slides gốc | Xử lý như Docs/Sheets: `/preview` + nút mở tab mới | Cùng nhóm file Google gốc |
| 2 | Khi trình duyệt chưa đăng nhập Google | Hiện hướng dẫn + nút mở Google ở tab mới | `/preview` cần phiên đăng nhập Google |
| 3 | Vị trí dữ liệu MongoDB | Bind mount vào thư mục WSL2 (`MONGO_DATA_DIR`) thay vì named volume | Vị trí rõ ràng, dễ kiểm soát. Đổi sang named volume được nếu bạn muốn dọn bằng `down -v` |
| 4 | Cách backup DB | Script Python qua backend, lưu cục bộ + Drive | Chạy giống nhau trên Windows/Ubuntu, không cần `mongodump` |
| 5 | Nơi lưu refresh token Drive | **MongoDB (mã hóa)** thay vì `.env` | Cho phép cấp quyền lại ngay trong app. Đổi sang `.env` được nếu bạn thích gọn hơn |
| 6 | Danh sách Workspace | Lấy từ Drive; MongoDB chỉ lưu thứ tự; tên không được trùng | Folder tạo trực tiếp trên Drive tự thành Workspace |
| 7 | Workspace sau khi đăng nhập | Chưa có Workspace đang chọn thì luôn vào màn hình Workspace | Khớp mô tả "vào MyHub phải tạo/chọn Workspace trước" |
| 8 | Phạm vi tìm kiếm | Tìm theo tên trong **thư mục đang xem**; mở rộng ra cả Workspace nếu hiệu năng cho phép | Drive không có truy vấn "cả cây thư mục" trực tiếp |
| 9 | Giới hạn editor | File text/code dưới **5 MB** mới mở bằng editor; nhóm text gồm cả `md`, `csv`, `json`, `log`, `yaml` | Tránh treo trình duyệt |
| 10 | Cache PDF | Có, trong `data/cache`, giới hạn dung lượng; bản sao tạm trên Drive xóa vĩnh viễn ngay sau khi xuất | Xem lại nhanh, không để rác |
| 11 | Share: phần mở rộng | Liệt kê/đổi/gỡ quyền; cảnh báo khi Anyone + Editor; tùy chọn gửi email thông báo | Cần để quản lý chia sẻ đầy đủ |
| 12 | Ngoài v1 | Di chuyển/sao chép, tải folder zip, UI thùng rác, UI lịch sử phiên bản | Giữ v1 gọn |
| 13 | Container | `restart: "no"` | Bạn muốn tự start thủ công |
| 14 | Phiên bản công nghệ | Chốt chính xác khi viết code, sau khi xác minh | Tránh dùng thông tin cũ |

---

## 20. Kết luận

1. Các phần có đánh dấu là [Yêu cầu] thì bắt buộc phải làm theo đúng quy định đã nói trong tài liệu. Các phần có đánh dấu là [Đề xuất] thì AI hãy làm theo cách giải quyết nếu có nói đến trong liệu, nếu không có thì hãy tự đưa ra quyết định mà không cần hỏi lại và chỉ cần báo cáo lại cho tôi chính xác bạn đã tự đưa ra quyết định gì.
2. Sau khi hiểu và suy luận xong thì bắt đầu viết code phiên bản đầu theo đúng quy ước ở mục 17, kèm `README.md` hướng dẫn chạy chi tiết.
