# MyHub v0.1

Ứng dụng cá nhân quản lý cùng bộ tệp Google Drive trên nhiều thiết bị. backend FastAPI chạy trong venv, frontend React/TypeScript, MongoDB chạy riêng bằng Docker Engine trong WSL2. **Tệp gốc luôn ở Drive; MongoDB chỉ giữ metadata phụ trợ.**

`MyHub_README.md` là tài liệu yêu cầu gốc, được giữ nguyên. File này hướng dẫn chạy mã nguồn đã xây dựng.

Kết quả kiểm tra và giới hạn xác minh nằm trong [VERIFICATION.md](VERIFICATION.md).

Triển khai VPS, Cloudflare Tunnel và CI/CD: xem [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md). Production dùng chung hostname `myhub.liamcao.io.vn`; local vẫn chạy thủ công. Upload giao diện dùng phiên resumable với các request tối đa 8 MiB để tải file lớn qua Cloudflare Free; có retry và tiếp tục trong cùng tab khi chọn lại file sau lỗi/reload.

Logo giao diện và favicon dùng chung `frontend/public/myhub_logo.png`. File này là bản sao ảnh người dùng cung cấp tại `data/images/myhub_logo.png`, được đưa vào frontend để phục vụ khi chạy dev và build production. Khi đổi logo, cập nhật bản trong `frontend/public/`; thư mục `data/` vẫn được Git bỏ qua.

Biểu tượng nút chọn Workspace dùng `frontend/public/select_workspace_icon.png`, sao chép từ ảnh trong `data/images/`. CSS dùng độ trong suốt của ảnh làm mặt nạ và lấy màu theo theme để hiển thị rõ trên cả light/dark mode, gồm Panel thu gọn.

### Cập nhật giao diện và tên thư mục 04/11/2026

- Hai thư mục mã nguồn dùng tên chữ thường `backend/` và `frontend/`. Các lệnh và đường dẫn bên dưới đã được cập nhật, dùng đúng chữ thường trên Linux/WSL2.
- Trang Workspace dùng lời chào cố định **Liam Cao** (Việt/Anh theo ngôn ngữ giao diện); tên này chỉ phục vụ hiển thị, không đổi profile hoặc whitelist OAuth.
- Tăng 1 px cho chữ nhỏ, giữ kích thước vùng nội dung; dropdown dùng chung góc bo/theme và hỗ trợ bàn phím.
- Bộ chọn Workspace trên Panel mở danh sách và vào thẳng Files của Workspace được chọn, gồm cả Panel thu gọn.
- Không sửa ba `.env` cá nhân. Không có giá trị nào trong các file đó chứa tên thư mục cũ khi kiểm tra lần chuyển đổi này. `LOCAL_DATA_DIR=../data`, URL API và OAuth callback không phụ thuộc việc đổi tên thư mục.

**Chạy lại:** mở terminal mới trong `backend/` và `frontend/`, dùng các lệnh ở mục 7. Nếu đang dùng terminal đã kích hoạt venv, thoát rồi kích hoạt lại tại đường dẫn mới. Shortcut, task IDE hoặc script riêng nằm ngoài repo cần tự cập nhật nếu đã ghi cứng đường dẫn cũ; không cần tạo lại khóa hay cấp lại quyền Drive vì thay đổi này.

## 1. Phạm vi đã chốt

- Google `cdtanhh@gmail.com` (email đã xác minh) hoặc GitHub `cdtanhh1807`; tài khoản khác bị từ chối ở backend.
- Quyền Drive của chủ tài khoản được cấp riêng một lần, refresh token mã hóa trong MongoDB. Đăng nhập GitHub vẫn dùng cùng Drive.
- Workspace lấy trực tiếp từ các folder con của root Drive; tạo/đổi tên, sắp xếp tên/ngày, kéo thả và xóa hai bước.
- Duyệt folder, breadcrumb, tìm tên trong folder hiện tại, sort, list/grid, upload nhiều file có tiến trình, download/stream Range, rename, trash, restore.
- Di chuyển tệp/folder; sao chép **tệp** giữa folder hoặc Workspace. Không sao chép đệ quy folder.
- Chia sẻ email/link, đổi role/gỡ quyền, tùy chọn gửi email, sao chép link Drive.
- CodeMirror 6 cho UTF-8 text/code tối đa 5 MB mặc định; save cùng ID, kiểm tra version, chọn overwrite/reload/copy khi xung đột.
- PDF có zoom/chuyển trang; ảnh có zoom/prev/next; HTML5 video/audio; Google Docs/Sheets/Slides dùng `/preview`; Office chuyển PDF hoặc fallback Drive.
- Thùng rác Workspace/file và lịch sử revision. File Google gốc mở lịch sử/khôi phục trong trình chỉnh sửa Google.
- Folder archive: **ZIP, RAR, 7z, TAR, GZ, TGZ, JAR, ISO**. GZ/TGZ chứa TAR; JAR là ZIP; ISO là ảnh đĩa dữ liệu, không phải đĩa boot. Tên không hợp lệ trên Windows được chuẩn hóa khi đóng gói; tên trùng được thêm hậu tố. Rock Ridge giữ tên đầy đủ trong ISO, Joliet có tên rút gọn.
- Việt/Anh, Sáng/Tối/Theo hệ thống; màn hình ngang có sidebar trái, màn hình dọc có bottom navigation và Account bottom-sheet.
- Backup/restore Python, Compose MongoDB, cấu hình `.env`, hướng dẫn Windows/Ubuntu và cleanup.

**Quyết định sau khi hỏi người dùng:** mục 2.1 được ưu tiên so với dòng 12 mục 19 của tài liệu gốc. Nhóm thao tác nâng cao và toàn bộ định dạng archive kể trên nằm trong v1. Người dùng đồng ý tự cài 7-Zip và WinRAR/RAR CLI với giấy phép phù hợp; app dùng `data/tmp` rồi dọn khi tải xong/lỗi.

Chưa có Q&A, Gmail, task/remind/checklist, PWA/Android hoặc triển khai hosting. Các tính năng này chưa có code giả hoặc nút không hoạt động trong UI.

## 2. Điều kiện trước khi chạy

| Thành phần | Cấu hình |
|---|---|
| Python | 3.12 hoặc 3.13; môi trường hiện tại đã kiểm thử với **3.13.12** |
| Node.js | **22.12+**; đã build với 22.23.3 |
| npm | Dùng `npm.cmd` trong PowerShell để tránh lỗi policy chặn `npm.ps1` |
| MongoDB | Compose cố định **mongo:8.0.34**, bind mount ext4 trong WSL2 |
| Windows dev | WSL2 + Ubuntu + Docker Engine trong distro, không cần Docker Desktop |
| Archive 7z/RAR | 7-Zip CLI và WinRAR/RAR CLI cài trên **máy chạy backend**, không phải container MongoDB |
| Google | OAuth Web application, Drive API bật, folder root riêng |
| GitHub | OAuth App riêng cho MyHub |

Các thư viện Python được khóa cả phụ thuộc gián tiếp trong `backend/requirements.txt`; npm khóa trong `frontend/package-lock.json` (dùng `npm ci`). Stack chính đã cài: FastAPI 0.162.0, PyMongo 4.19.0, React 19.3.1, Vite 8.3.5, TypeScript 7.0.2. Đây là các phiên bản được khóa để tái lập, không dùng tag `latest`.

[Vite ghi yêu cầu Node](https://vite.dev/guide/). [MongoDB 8.0.34 release notes](https://www.mongodb.com/docs/v8.0/release-notes/8.0/) là cơ sở chọn patch MongoDB.

## 3. Ba file môi trường

Không commit `.env`. Chỉ commit `.env.example`; frontend tuyệt đối không nhận OAuth secret, Mongo URI, JWT secret hoặc encryption key.

**PowerShell, ở thư mục gốc MyHub:**

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env
```

**Ubuntu/WSL2, ở thư mục gốc:**

```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

### 3.1. `/.env`: hạ tầng Docker

| Biến | Cách điền |
|---|---|
| `MONGO_ROOT_USERNAME` | Tự đặt, ví dụ `myhub_root` |
| `MONGO_ROOT_PASSWORD` | Mật khẩu root ngẫu nhiên, khác mật khẩu app |
| `MONGO_APP_USERNAME` | Tự đặt, ví dụ `myhub_app` |
| `MONGO_APP_PASSWORD` | Mật khẩu riêng cho backend, tạo ngẫu nhiên |
| `MONGO_DB_NAME` | Mặc định `myhub` |
| `MONGO_PORT` | Mặc định `27017`, chỉ bind `127.0.0.1` |
| `MONGO_DATA_DIR` | Đường dẫn **Linux tuyệt đối** trong ext4 WSL2, ví dụ `/home/your-user/myhub-data/mongodb`; không dùng `/mnt/c/...` |

Sinh từng mật khẩu trên Windows hoặc Ubuntu (chạy hai lần để có hai mật khẩu khác nhau):

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Ubuntu dùng `python3` nếu không có alias `python`. Có thể dùng `openssl rand -base64 32`; với base64, phải URL-encode mật khẩu khi ghép URI MongoDB.

### 3.2. `/backend/.env`: backend

| Biến | Cách lấy/ý nghĩa |
|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google Cloud Console → project MyHub → Google Auth Platform/Clients hoặc APIs & Services → Credentials → OAuth Web client |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | Mở folder root riêng trên Drive, lấy phần ID trong URL `/drive/folders/ID` |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | GitHub → Settings → Developer settings → OAuth Apps → New OAuth App |
| `ALLOWED_GOOGLE_EMAIL` | Giữ `cdtanhh@gmail.com` |
| `ALLOWED_GITHUB_USERNAME` | Giữ `cdtanhh1807`; kiểm tra username, không kiểm tra numeric ID |
| `MONGODB_URI` | Khớp username/password/DB trong `.env` gốc; backend dùng user app, không dùng root |
| `MONGODB_DB_NAME` | Khớp `MONGO_DB_NAME`, mặc định `myhub` |
| `JWT_SECRET_KEY` | Chuỗi ngẫu nhiên tối thiểu 32 ký tự; lệnh tạo bên dưới |
| `ENCRYPTION_KEY` | Khóa Fernet, sinh sau khi cài requirements; giữ nguyên khi chuyển máy |
| `BACKEND_URL` | `http://localhost:8000`, không có `/api/v1` hoặc dấu `/` cuối |
| `FRONTEND_URL` | `http://localhost:5173`, không có dấu `/` cuối |
| `CORS_ORIGINS` | JSON array, ví dụ `["http://localhost:5173"]` |
| `COOKIE_SECURE` | `false` cho HTTP localhost; `true` cho HTTPS |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Mặc định `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Mặc định `30`; refresh token xoay mỗi lần dùng |
| `DRIVE_SYSTEM_FOLDER_NAME` | `.myhub-system`, phải dành riêng cho app |
| `LOCAL_DATA_DIR` | `../data`, đường dẫn tương đối được tính từ `backend/` |
| `MAX_EDIT_FILE_SIZE_MB` | Mặc định `5`, tối đa `20` |
| `PDF_CACHE_MAX_MB` | Mặc định `256`; `0` để bỏ bản cache sau khi stream |
| `ARCHIVE_MAX_MB` | Mặc định `2048`; giới hạn tổng đầu vào/đầu ra mỗi job |
| `ARCHIVE_MAX_FILES` | Mặc định `10000`; cũng bảo vệ việc duyệt cây quá lớn |
| `ARCHIVE_TIMEOUT_SECONDS` | Mặc định `1800`; timeout tiến trình CLI đóng gói |
| `SEVEN_ZIP_PATH`, `RAR_PATH` | Tên command trong PATH hoặc đường dẫn executable tuyệt đối, xem phần 6 |
| `OFFICE_PREVIEW_RULES` | JSON mapping từng extension thành `pdf` hoặc `drive` |

Ví dụ Mongo URI khi dùng mật khẩu chỉ gồm ký tự URL-safe:

```dotenv
MONGODB_URI=mongodb://myhub_app:YOUR_APP_PASSWORD@localhost:27017/myhub?authSource=myhub
```

Nếu mật khẩu có ký tự đặc biệt, dùng `urllib.parse.quote_plus` để encode **phần mật khẩu**, không encode cả URI:

```bash
python -c "from getpass import getpass; from urllib.parse import quote_plus; print(quote_plus(getpass('Mongo app password: ')))"
```

Sinh JWT secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Sinh encryption key **trong venv sau khi cài requirements**:

```powershell
# PowerShell, ở backend/
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```bash
# Ubuntu, ở backend/
.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Mỗi lệnh in ra một giá trị riêng để dán vào `.env`; không đưa các giá trị đó lên chat hoặc Git. App báo lỗi cấu hình và dừng startup nếu thiếu khóa/URI. Không có chế độ bỏ qua xác thực hoặc dữ liệu demo trong runtime.

### 3.3. `/frontend/.env`: frontend

```dotenv
VITE_API_BASE_URL=/api/v1
```

Khi dev, Vite proxy `/api` tới `http://localhost:8000`. Giữ cách này để OAuth cookie, media, video và download dùng cùng origin với giao diện. Không trộn `127.0.0.1` và `localhost`: **mở UI bằng `http://localhost:5173`**. Nếu đổi backend port, sửa target trong `frontend/vite.config.ts` và các URL/env/redirect tương ứng.

## 4. OAuth Google, GitHub và quyền Drive

### Google Cloud

1. Chọn/tạo project MyHub, bật **Google Drive API** trong API Library.
2. Cấu hình OAuth consent screen: tên app MyHub, email hỗ trợ/chủ app của bạn.
3. Tạo OAuth client loại **Web application**. Authorized JavaScript origin: `http://localhost:5173`.
4. Đăng ký **hai Authorized redirect URIs chính xác**:

   ```text
   http://localhost:8000/api/v1/auth/google/callback
   http://localhost:8000/api/v1/auth/drive/callback
   ```

5. Dán Client ID/secret vào `backend/.env`.
6. Chuyển publishing status của OAuth consent screen từ **Testing sang In production**. Token Drive có scope rộng nên ở Testing có thể hết hạn sau 7 ngày. App cá nhân có thể gặp màn hình chưa được xác minh; chỉ tiếp tục với đúng client/project bạn sở hữu. Các chính sách tài khoản tổ chức có thể vẫn chặn scope.

Luồng đăng nhập chỉ xin profile/email; luồng **Kết nối Google Drive** xin thêm `https://www.googleapis.com/auth/drive` với offline access. backend chỉ nhận chủ Google đã xác minh có email đúng whitelist. Không dùng Service Account hoặc `drive.file`.

[Google mô tả Authorization Code/offline access](https://developers.google.com/identity/protocols/oauth2/web-server) và [giới hạn refresh token khi Testing](https://developers.google.com/identity/protocols/oauth2).

### GitHub

1. GitHub → Settings → Developer settings → OAuth Apps → **New OAuth App**.
2. Application name: `MyHub`; Homepage URL: `http://localhost:5173`.
3. Authorization callback URL:

   ```text
   http://localhost:8000/api/v1/auth/github/callback
   ```

4. Register application → Generate client secret → điền Client ID/secret vào backend env.

backend xin `read:user` và chỉ đối chiếu `login=cdtanhh1807`. Đăng nhập GitHub không xin quyền Drive của GitHub; nó dùng credential Google chủ sở hữu đã lưu mã hóa.

[Hướng dẫn OAuth App chính thức của GitHub](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app).

### Kết nối Drive lần đầu

Đăng nhập MyHub → **Kết nối Google Drive** → chọn `cdtanhh@gmail.com` → đồng ý scope. Việc này chỉ khởi động từ một phiên MyHub hợp lệ; callback kiểm tra phiên đó, state, PKCE và email Google đã xác minh. Nếu Google không trả refresh token, cấp lại qua Account → Kết nối Google Drive.

Tạo folder root riêng trên Drive và đặt đúng ID. Không tự tạo, di chuyển hoặc xóa `.myhub-system`; thư mục này chứa backup và bản chuyển đổi tạm, bị ẩn/chặn ở toàn bộ API file/Workspace.

Nếu iframe Google không hiển thị, đăng nhập Google bằng tài khoản có quyền trong trình duyệt hoặc dùng nút **Mở trong Google**. Không đổi file thành public chỉ để xem trước.

## 5. Chạy lần đầu trên Windows + WSL2

### Terminal 1 — WSL2 Ubuntu, MongoDB

Chuyển đến dự án bằng đường dẫn WSL, ví dụ:

```bash
cd /mnt/c/Users/YOUR_WINDOWS_USER/Documents/Workspace/MyHub
mkdir -p /home/YOUR_WSL_USER/myhub-data/mongodb
docker compose up -d
docker compose ps
docker compose logs --tail 50 mongodb
```

Thư mục `mkdir` phải khớp `MONGO_DATA_DIR` trong `.env`. Compose không tự tạo host path để tránh vô tình tạo trên ổ Windows. Docker daemon phải đang chạy trong WSL2 trước lệnh Compose.

Container `myhub-mongodb`: RAM tối đa 1 GB, WiredTiger cache 0.25 GB, log tối đa 3 × 10 MB; port `127.0.0.1:27017`. `restart: "no"`, không tự restart app/container. Script init tạo user app chỉ có `readWrite` trên DB MyHub.

**Init user chỉ chạy khi `/data/db` rỗng.** Đổi mật khẩu trong `.env` sau lần đầu không tự đổi tài khoản đã tạo. Muốn đổi cần dùng mongosh với root để đổi mật khẩu rồi cập nhật backend URI; không xóa data để chữa lỗi đăng nhập.

### Terminal 2 — Windows PowerShell, backend

```powershell
cd C:\Users\YOUR_WINDOWS_USER\Documents\Workspace\MyHub\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt
```

Sau đó sinh `ENCRYPTION_KEY` bằng lệnh ở mục 3, hoàn thành `backend/.env`, rồi chạy:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

Dùng trực tiếp Python trong venv nên không cần đổi PowerShell ExecutionPolicy. Nếu muốn kích hoạt venv khi policy cho phép: `.\.venv\Scripts\Activate.ps1`. `--no-access-log` tránh ghi OAuth code và state trong URL callback vào log request. Chạy **một worker** ở v1.

Kiểm tra `http://localhost:8000/api/v1/health`; OpenAPI ở `http://localhost:8000/docs`. Startup ping MongoDB và tạo TTL index, nên cấu hình DB sai sẽ dừng startup thay vì chạy ở trạng thái kết nối giả.

### Terminal 3 — Windows PowerShell, frontend

```powershell
cd C:\Users\YOUR_WINDOWS_USER\Documents\Workspace\MyHub\frontend
npm.cmd ci
npm.cmd run dev
```

Mở **http://localhost:5173** → đăng nhập → kết nối Drive → chọn/tạo Workspace. Không có Workspace được chọn thì bắt đầu tại trang chọn Workspace. Có thể mở URL `/files?workspace=DRIVE_FOLDER_ID&folder=CHILD_FOLDER_ID`; server vẫn kiểm tra từng ID.

### Nếu Windows không kết nối được MongoDB trong WSL2

Trong Windows kiểm tra `Test-NetConnection localhost -Port 27017`; trong WSL kiểm tra `docker compose ps` và `docker compose logs`. Xác minh cả ba env có cùng app user/password/DB. Kiểm tra cơ chế localhost forwarding/mirrored networking của WSL, Docker bind loopback và khởi động lại WSL sau khi thay cấu hình. Không mở MongoDB ra `0.0.0.0` để khắc phục. Có thể chạy backend trong cùng WSL2 theo hướng dẫn Ubuntu bên dưới để dùng localhost trong cùng Linux.

## 6. Công cụ archive

backend dùng Python stdlib cho ZIP/JAR/TAR/GZ/TGZ và `pycdlib` cho ISO. Hai định dạng sau cần CLI ngoài, như đã xác nhận:

- **Windows:** cài [7-Zip từ trang chính thức](https://www.7-zip.org/download.html) và [WinRAR từ RARLAB](https://www.rarlab.com/download.htm). Đặt `SEVEN_ZIP_PATH=C:/Program Files/7-Zip/7z.exe` và `RAR_PATH=C:/Program Files/WinRAR/Rar.exe` trong backend env nếu chưa có PATH.
- **Ubuntu:** dùng bản CLI Linux chính thức tương ứng, giải nén vào vị trí bạn kiểm soát. Có thể đặt `SEVEN_ZIP_PATH=/home/your-user/tools/7zip/7zz` và `RAR_PATH=/home/your-user/tools/rar/rar`; cấp quyền executable. RAR phải có giấy phép phù hợp. Không cần cài CLI vào container MongoDB.

Khởi động lại backend sau khi sửa env. API `/api/v1/archive-formats` kiểm tra executable; định dạng thiếu công cụ bị vô hiệu hóa trong hộp thoại tải folder. MyHub không tự cài hoặc mua giấy phép.

Tải archive mở tab download của browser. backend stream từng nguồn Drive xuống một workspace riêng trong `data/tmp`, sau đó đóng gói và stream kết quả; không đọc toàn bộ nội dung vào RAM. Mỗi tiến trình chỉ chạy một job archive. Cần dung lượng trống ít nhất `2 × ARCHIVE_MAX_MB` khi bắt đầu; giới hạn tổng số mục và byte được kiểm tra thêm khi tải. Nếu server bị tắt đột ngột, phần tạm có thể còn lại; dừng backend rồi xóa riêng `data/tmp/archive-*`. Không xóa backup.

## 7. Các lần chạy sau và Ubuntu

**WSL2**, ở gốc dự án:

```bash
docker compose start mongodb
docker compose ps
```

**Windows backend**, ở `backend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

**Windows frontend**, ở `frontend/`:

```powershell
npm.cmd run dev
```

Không cần cài lại package nếu lockfile/requirements không đổi. Dừng mỗi server bằng `Ctrl+C`; dừng DB bằng `docker compose stop mongodb` trong WSL2. Dùng `docker compose down` nếu muốn gỡ container/network nhưng vẫn giữ dữ liệu bind mount.

**Ubuntu native**, sau khi tạo ba env và thư mục Mongo ext4 đúng cấu hình:

```bash
# Terminal DB, ở gốc
docker compose up -d

# Terminal backend
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -r requirements.txt
.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log

# Terminal frontend mới, ở gốc repo
cd frontend
npm ci
npm run dev
```

Lần sau bỏ bước tạo venv/cài dependencies, dùng `docker compose start mongodb`. Không dùng lại venv/node_modules của Windows trên Ubuntu; tạo mới từ requirements/lockfile.

Deploy domain/reverse proxy/HTTPS chưa nằm trong v1. Khi làm bước đó, giữ cùng origin cho frontend/API, đổi URL/CORS/cookie Secure và đăng ký callback tương ứng trên Google/GitHub. API nghiệp vụ đã hỗ trợ `Authorization: Bearer` để tái sử dụng cho client khác; refresh web hiện dùng httpOnly cookie và kiểm tra Origin.

## 8. Backup, restore, chuyển máy

Chạy CLI trong môi trường backend với `.env` đã cấu hình. MongoDB phải chạy. Để snapshot metadata nhất quán, dừng backend trước khi backup/restore; CLI tự kết nối DB/Drive nên không cần server API chạy. CLI không backup nội dung file Drive.

### Backup

```powershell
# Windows, tại backend/
.\.venv\Scripts\python.exe scripts/backup_db.py
```

```bash
# Ubuntu, tại backend/
.venv/bin/python scripts/backup_db.py
```

Kết quả: `data/backups/backup-<UTC timestamp>.jsonl.gz` và một file cùng tên trong folder hệ thống Drive. BSON Extended JSON giữ được datetime/ObjectId; xuất theo từng document, không cần mongodump. Nếu upload Drive lỗi, bản local đã tạo vẫn được giữ và CLI báo lỗi. Backup có metadata riêng tư và token Drive đã mã hóa; giữ `ENCRYPTION_KEY` trong trình quản lý mật khẩu để dùng lại.

### Restore từ local

```powershell
.\.venv\Scripts\python.exe scripts/restore_db.py ../data/backups/YOUR_BACKUP.jsonl.gz --confirm-replace
```

```bash
.venv/bin/python scripts/restore_db.py ../data/backups/YOUR_BACKUP.jsonl.gz --confirm-replace
```

### Restore từ Drive

```powershell
.\.venv\Scripts\python.exe scripts/restore_db.py --from-drive latest --confirm-replace
```

```bash
.venv/bin/python scripts/restore_db.py --from-drive latest --confirm-replace
```

Có thể thay `latest` bằng ID backup nằm trực tiếp trong folder hệ thống. Restore chỉ đọc backup trong folder đó, không tải ID tùy ý ngoài root. CLI validate toàn bộ archive trước khi ghi, nạp staging rồi rename từng collection; **không phải transaction toàn database**. Giữ backup hiện trạng trước khi thay dữ liệu.

Mặc định không ghi đè `drive_credentials`, không phục hồi session/OAuth state và thu hồi các phiên hiện tại sau khi restore. Muốn lấy credential từ backup local, thêm `--include-drive-credentials` và dùng đúng encryption key cũ. TTL indexes được tạo lại khi hoàn tất.

### Sang máy mới

1. Clone/pull repo private của bạn; không đưa `.env`, data, venv hoặc node_modules lên GitHub.
2. Tạo lại ba env. Giữ nguyên `ENCRYPTION_KEY`, root folder ID và các giá trị OAuth; sửa đường dẫn Mongo/CLI nếu khác máy.
3. Start MongoDB bằng Compose; tạo venv và cài requirements, chạy frontend/backend như mục 5/7.
4. Đăng nhập và cấp Drive một lần trên DB mới.
5. Dừng backend; chạy restore `--from-drive latest --confirm-replace` để giữ credential vừa cấp.
6. Khởi động backend và đăng nhập lại. Workspace/file luôn được dựng lại từ Drive.

Nếu mất encryption key, cấp Drive lại. Mất MongoDB không làm mất file Drive, nhưng mất setting, thứ tự tùy chọn và phiên nếu không restore backup.

## 9. Cấu trúc và mục đích file

| File/thư mục | Mục đích |
|---|---|
| `MyHub_README.md` | Yêu cầu gốc, không sửa |
| `README.md` | Hướng dẫn cài/chạy/vận hành này |
| `VERIFICATION.md` | Kết quả test, ảnh QA và các tích hợp còn cần cấu hình live |
| `docker-compose.yml` | MongoDB loopback, bind mount, RAM/cache/log, restart thủ công |
| `.env.example`, `backend/.env.example`, `frontend/.env.example` | Ba mẫu cấu hình thuộc ba thành phần riêng |
| `.gitignore`, `.gitattributes` | Loại secrets/runtime/dependencies, chuẩn hóa LF |
| `docker/mongo-init/01-create-app-user.js` | Tạo user app hạn chế quyền khi DB rỗng |
| `scripts/cleanup.sh` | Dọn hạ tầng WSL2 với kiểm tra path và xác nhận xóa |
| `data/.gitkeep` | Giữ nơi chứa runtime; nội dung data không commit |
| `backend/requirements.txt`, `pytest.ini` | Khóa dependencies Python và cấu hình test async |
| `backend/app/main.py` | App factory/lifespan, dependency wiring, CORS và exception handlers |
| `app/config/settings.py` | Validate env/khóa, chuẩn hóa path bằng pathlib |
| `app/core/errors.py`, `dependencies.py` | Lỗi miền, Bearer/media/Origin ở biên HTTP |
| `app/core/streaming.py` | Response bảo đảm đóng upstream và dọn tmp kể cả client ngắt kết nối |
| `app/models/records.py` | Model nội bộ cho stream nguồn dữ liệu |
| `app/dtos/contracts.py` | DTO Request/Response/file/list/stream và validation |
| `app/controllers/auth.py`, `workspaces.py`, `files.py` | Router auth/Workspace/settings/file/preview/share; tạo DTO trước khi gọi Service |
| `app/services/auth.py` | Whitelist, state/PKCE, phiên JWT/refresh, Drive credential mã hóa |
| `app/services/scope.py` | Duyệt chuỗi cha, bảo vệ root/Workspace/system/shortcut |
| `app/services/workspaces.py` | Workspace CRUD, thứ tự/settings, snapshot xóa hai bước |
| `app/services/files.py` | File CRUD, stream, text save/conflict, transfer, trash/revision |
| `app/services/sharing.py` | Nghiệp vụ permissions Drive |
| `app/services/preview.py` | Viewer classification, Office conversion, cache PDF |
| `app/services/archive.py` | Archive Python/CLI, giới hạn byte/file và cleanup |
| `app/repositories/mongo.py`, `drive.py`, `oauth.py` | Mọi thao tác MongoDB/Drive/OAuth, REST pagination và streaming |
| `app/utils/files.py` | MIME, extension, ID validation và Unicode filename header |
| `backend/scripts/_runtime.py`, `backup_db.py`, `restore_db.py` | Runtime CLI, export gzip JSONL, restore staging |
| `backend/tests/conftest.py`, `test_security.py`, `test_storage.py`, `test_backup.py` | Fake nguồn dữ liệu, kiểm tra security, archive/stream thật và BSON backup |
| `frontend/package.json`, `package-lock.json`, `.npmrc` | Lệnh npm, khóa package, cache npm đặt trong dự án |
| `frontend/index.html`, `vite.config.ts`, `tsconfig.json` | Entry HTML, React/Tailwind/proxy, strict TypeScript |
| `frontend/src/main.tsx`, `app/App.tsx` | Query/router providers, login, shell, Account, điều phối màn hình |
| `src/pages/Workspaces.tsx`, `Files.tsx`, `Trash.tsx` | Trang danh sách Workspace, file và khôi phục trash |
| `src/features/files/Dialogs.tsx` | Tên/xóa/share/destination/archive/history/details dialogs |
| `src/features/preview/Viewer.tsx` | Bảng đăng ký viewer và CodeMirror/PDF/image/Drive/media components |
| `src/components/ui.tsx` | Modal native/focus trap, trạng thái trống/loading, menu, icon, toast |
| `src/components/Select.tsx` | Dropdown/listbox bo góc dùng chung, keyboard, typeahead và portal trong dialog |
| `src/features/workspaces/WorkspaceSwitcher.tsx` | Chọn Workspace trực tiếp trên Panel bằng Drive folder ID |
| `src/services/api.ts` | Adapter API duy nhất, refresh đồng thời, media cookie/download |
| `src/store/session.ts`, `hooks/usePreferences.ts` | Zustand token trong RAM, setting Mongo và theme theo hệ thống |
| `src/i18n/index.ts`, `theme/app.css` | Việt/Anh, token sáng/tối và layout theo orientation |
| `src/types/index.ts`, `utils/format.ts` | Hợp đồng TypeScript và định dạng size/time |
| `frontend/playwright.config.ts`, `tests/app.spec.ts` | Kiểm thử Edge có API giả lập, không dùng tài khoản Drive thật |
| Các `__init__.py` | Đánh dấu package Python, không có side effects |

Luồng backend: **Controller → DTO Request → Service → Repository → MongoDB/Drive → Service tạo DTO Response → Controller**. StreamDTO mang iterator/header, Controller mới bọc StreamingResponse. Service không nhận FastAPI Request/Response.

Tính năng tương lai dùng `workspace_id`/`drive_file_id`, thêm module cùng khuôn và tái sử dụng DriveRepository/ScopeService. Không đưa dữ liệu suy ra được từ Drive thành nguồn chính trong Mongo.

## 10. Dữ liệu và kiểm soát truy cập

- Mọi thao tác file lần theo chuỗi parent đến đúng Workspace, Workspace phải là folder con trực tiếp root. System folder/root ngoài phạm vi không thể đọc/ghi qua API file. Transfer xác thực cả nguồn và đích.
- Shortcut Drive bị chặn để không truy cập nội dung đích bên ngoài cây.
- Access JWT trong RAM, refresh cookie httpOnly/SameSite và hash lưu DB; refresh rotate dùng consume nguyên tử. Mỗi API kiểm tra phiên chưa hết hạn/chưa logout.
- Media cookie 30 phút chỉ đọc content/PDF/archive/revision của **một file** đã được cấp bằng Bearer. Nó không cấp quyền mutate hoặc xem metadata của file khác. Viewer đang mở làm mới cookie định kỳ. Video/download đi bằng browser streaming, không gom file lớn vào Blob.
- Workspace delete dùng snapshot token có hạn 5 phút, xem ảnh hưởng rồi nhập đúng tên. Cây thay đổi giữa hai bước yêu cầu xác nhận lại. Đây là kiểm tra ứng dụng, không phải transaction khóa toàn bộ cây Drive.
- Text save kiểm tra version trước ghi và tuần tự hóa save trong **một process**. Google Drive không cung cấp transaction cho toàn bộ read-compare-write này; sửa trực tiếp Drive đúng khoảng so sánh/ghi vẫn có thể cạnh tranh. Chạy một worker v1. Lịch sử revision không thay thế backup lâu dài.
- Office conversion import lại binary vào bản Google tạm thay vì đổi MIME trực tiếp file gốc; luôn cố xóa bản tạm trong `finally`. Nếu upstream xóa tạm lỗi hoặc tiến trình bị tắt đột ngột, kiểm tra folder hệ thống để dọn bản `preview-*`; không xóa backup.
- File UTF-8 không quá giới hạn editor mới đọc vào RAM. Upload, download, video, revision và export truyền chunk. Cache PDF là dữ liệu dẫn xuất có giới hạn; archive là dữ liệu tạm.

Collections: `users`, `user_settings`, `workspace_orders`, `drive_credentials`, `refresh_sessions`, `oauth_states`, `system_state`. `oauth_states` bổ sung để state/PKCE có TTL và dùng một lần, không cần lưu token provider vào cookie.

## 11. Kiểm thử và giới hạn xác minh

**backend**, tại `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

**frontend**, tại `frontend/`:

```powershell
npm.cmd run build
# Trong terminal khác, giữ npm.cmd run dev đang chạy ở localhost:5173:
npm.cmd exec -- playwright test
```

Ubuntu dùng `npm run build` và `npm exec -- playwright test`. Playwright mặc định dùng Edge đã cài; nếu máy khác dùng Chromium, sửa `channel` trong `playwright.config.ts` hoặc cài browser theo nhu cầu. Test không tự start MongoDB/backend và không cài browser.

backend tests kiểm tra phạm vi/IDOR, whitelist, OAuth state, token encryption/rotation/logout, cookie scope, CSRF, Range, conflict, delete hai bước, chia sẻ, trash/restore, upload size, PDF fallback cleanup, BSON backup và nội dung ZIP/JAR/TAR/GZ/TGZ/ISO thật. Test RAR tự skip nếu không có công cụ; để chạy Windows có thể đặt `$env:MYHUB_TEST_RAR_PATH = 'C:\Program Files\WinRAR\Rar.exe'` trước lệnh pytest. Browser tests dùng API giả lập để kiểm tra editor/save/conflict, upload nhiều file, render/zoom PDF, xóa hai bước, orientation, Account, Việt/Anh và dark mode. Artifact QA nằm trong `data/previews`/`data/test-results`, không commit.

OAuth/Drive/MongoDB live cần credentials riêng trên máy chạy; các giá trị này không có trong repo. ZIP/JAR/TAR/GZ/TGZ/ISO và RAR đã được kiểm tra với nội dung thật; RAR dùng CLI có sẵn trên máy. 7z chưa được kiểm chứng bằng CLI vì chưa có 7-Zip. Nghiệm thu tích hợp live sau khi cấu hình mục 3–6: đăng nhập cả hai provider, upload/download file lớn, tua video, chuyển Office thật, thay quyền share, restore revision, backup/restore và thử 7z. Trình duyệt có thể không giải mã được một số codec MOV/video; dùng download nếu gặp giới hạn codec.

## 12. Dung lượng và gỡ sạch

| Nơi | Nội dung | Cách dọn |
|---|---|---|
| Repo Windows/Ubuntu | Source, `backend/.venv`, `__pycache__`, `.pytest_cache` | Xóa thư mục dự án sau khi dừng server |
| `frontend/` | `node_modules`, `.npm-cache`, `dist`, TypeScript build info | Nằm trong dự án; xóa cùng repo |
| `data/cache`, `data/tmp`, `data/backups`, `data/test-tmp`, artifacts QA | PDF dẫn xuất, archive tạm, backup local, dữ liệu test | Xóa cùng repo; giữ backup cần dùng trước |
| WSL2: `MONGO_DATA_DIR` | MongoDB persistent dữ liệu | Cleanup script hoặc xóa tay đúng path sau khi dừng container |
| Kho Docker WSL2 | Image `mongo`, container log/network | `docker compose down --rmi all` |
| Browser | Cookie, theme/lang | Clear site data cho localhost:5173 và localhost:8000 |
| Google Drive | File gốc, trash, backup/system folder | Gỡ app không tác động; nếu không dùng nữa tự quản lý trên Drive |
| Hệ thống | Python/Node/WSL/Docker và 7-Zip/RAR đã tự cài | Không thuộc dữ liệu MyHub; gỡ như phần mềm thông thường nếu muốn |

pip luôn dùng `--no-cache-dir`; `.npmrc` đưa npm cache vào `frontend/.npm-cache`. Docker lưu log trong data root của daemon; xem vị trí bằng `docker info --format '{{.DockerRootDir}}'` và `docker inspect myhub-mongodb --format '{{.LogPath}}'` trong WSL2. Bind mount nằm đúng đường dẫn bạn khai báo, không có named volume ẩn.

**Gỡ:**

1. Dừng frontend/backend bằng Ctrl+C. Giữ lại backup/env cần chuyển máy trước.
2. WSL2/Ubuntu, ở gốc repo: `bash scripts/cleanup.sh`. Script chỉ tự xóa path chuẩn `/home/<user>/myhub-data/mongodb`, in absolute path, yêu cầu gõ lại đúng path rồi mới `docker compose down --rmi all` và xóa data. Path tùy chỉnh bị từ chối; bạn tự kiểm tra và dọn riêng.
3. Xóa thư mục MyHub trên Windows/Ubuntu. Xóa site data trình duyệt nếu muốn.
4. Có thể thu hồi quyền MyHub tại Google Account → Security → Third-party connections và GitHub → Settings → Applications. Việc này không xóa file Drive.

### Thu gọn đĩa ảo WSL2 (tùy chọn, không tự chạy)

Xóa dữ liệu Linux không đảm bảo file VHDX trên Windows tự nhỏ lại. Xem [tài liệu quản lý đĩa WSL của Microsoft](https://learn.microsoft.com/en-us/windows/wsl/disk-space). Xác định đúng distro/VHDX và sao lưu distro cần giữ trước khi thao tác.

Trong WSL2 chạy `sudo fstrim -av`, thoát WSL. Trong **PowerShell Administrator** chạy `wsl --shutdown`. Nếu có module Hyper-V, dùng `Optimize-VHD -Path "ABSOLUTE_PATH_TO_YOUR_DISTRO_EXT4.vhdx" -Mode Full`. Nếu không có, mở `diskpart` rồi nhập từng dòng, thay đúng path đã xác minh:

```text
select vdisk file="ABSOLUTE_PATH_TO_YOUR_DISTRO_EXT4.vhdx"
attach vdisk readonly
compact vdisk
detach vdisk
exit
```

Không dùng `wsl --unregister` để thu gọn: lệnh đó xóa toàn bộ distro. MyHub không chạy thao tác thu gọn hoặc xóa dữ liệu hệ thống tự động.

## 13. Các lựa chọn triển khai tôi tự chốt

| Lựa chọn | Giá trị/lý do |
|---|---|
| Runtime kiểm chứng | Dùng Python 3.13.12 và Node 22.23.3 sẵn trên máy; code hỗ trợ Python 3.12+, bản 3.12 chưa được chạy trong môi trường này |
| Thư viện phụ trợ | Theo đề xuất: Vite/Tailwind, React Router/Query/Axios, Zustand/i18next, dnd-kit, CodeMirror, react-pdf; khóa phiên bản từ registry khi cài |
| PDF cache | 256 MB, key ID+version, tránh xóa bản đang được response khác dùng |
| Archive | 2 GB, tối đa 10.000 mục, một job/process; CLI timeout 30 phút; tmp xóa khi kết thúc hoặc ngắt socket |
| Text | UTF-8 không chứa NUL; 5 MB mặc định; không giải mã các encoding khác một cách suy đoán |
| Lưu text đồng thời | So version + khóa ghi một process; không tự ghi đè khi conflict |
| OAuth state | Collection `oauth_states` TTL 10 phút, browser binding + PKCE, consume một lần |
| Cookie media | Scope một file, 30 phút, chỉ GET nội dung; giữ streaming native browser và không đưa token vào URL |
| Refresh | Token rotate/hash, Web Locks chống hai tab cùng refresh; viewer làm mới media cookie khi session rotate |
| Restore | Validate trước, staging theo collection, bỏ phiên cũ và giữ credential Drive hiện tại mặc định |
| Hệ thống tệp | Shortcut bị chặn; tên archive được làm an toàn cho Windows/Ubuntu; folder copy đệ quy chưa có vì phạm vi yêu cầu là copy tệp |
| Vận hành | Local-only, một worker; không tự start container/server hay triển khai hosting |

Hai lựa chọn về phạm vi nâng cao và công cụ RAR/7z đã được người dùng xác nhận, không phải quyết định tự suy ra.
