# MyHub trên Ubuntu 22.04 — liamcao-vps

Đồng bộ đã chuyển sang SSE. Khi nâng cấp VPS đang chạy, xem [MYHUB_REALTIME_SYNC.md](../MYHUB_REALTIME_SYNC.md), đặc biệt bước cập nhật unit systemd có graceful shutdown và bật webhook Drive. Redis chỉ có hướng dẫn cho tương lai, chưa được triển khai.

Frontend và API dùng chung `https://myhub.liamcao.io.vn`: Nginx tách `/api/` sang backend. `cloudflared` chạy bằng service trên host và gọi `http://127.0.0.1:8080`. Không cần hostname API riêng. Backend vẫn là process riêng, không chạy bên trong frontend.

## Các file triển khai

| File | Mục đích |
|---|---|
| `nginx.conf` | SPA, API streaming và chính sách cache trên localhost:8080 |
| `myhub.service` | FastAPI một worker/venv, tự restart và chạy lúc boot |
| `myhub-sudoers` | User deploy chỉ được start/stop/restart/reset-failed service MyHub |
| `compose.production.yml` | MongoDB trên localhost, dữ liệu ngoài bản phát hành |
| `backend.env.example`, `mongo.env.example` | Mẫu cấu hình, không chứa bí mật |
| `init_config.py` | Sinh khóa và mật khẩu trên VPS mới, không ghi đè cấu hình cũ |
| `release.sh` | Kiểm checksum, chuẩn bị venv, switch release, health check và rollback code |
| `backup.sh` | Khóa deploy, dừng backend để snapshot nhất quán, chạy backup rồi bật lại |
| `../.github/workflows/myhub.yml` | CI cho PR/main; build artifact và deploy main khi đã bật |

## Bố trí và quyền

```text
/opt/myhub/
  releases/<COMMIT_SHA>/     # source và frontend/dist; .venv Python của riêng release
  current -> releases/...   # chỉ đổi symlink khi chuẩn bị thành công
  incoming/                 # tar.gz và checksum do Actions gửi
  shared/                   # mode 700, user myhub; giữ qua mọi lần deploy
    backend.env             # mode 600, tuyệt đối không commit
    data/                   # cache, tmp, backup local
    mongodb/                # Docker tự quản lý ownership bên trong
    bin/                    # uv
    python/                 # Python 3.13 managed
/etc/myhub/                 # root:root, mode 700
  mongo.env                 # mode 600
  compose.production.yml
  mongo-init/
```

User `myhub` không có password và không tham gia nhóm Docker. Nó chạy backend và nhận deploy qua SSH key riêng. Sudo chỉ cho các lệnh trong `myhub-sudoers`. Root cài service/Nginx/Mongo và script `/usr/local/bin/myhub-release`; artifact không tự cập nhật các file hệ thống đó. Khi thay đổi cấu hình hệ thống trong bản phát hành tương lai, quản trị viên xem diff và cài lại thủ công.

## 1. Chuẩn bị host (root)

Máy đích: Ubuntu 22.04 x86_64, 2 CPU, gần 4 GiB RAM; Docker/Compose và cloudflared đã có. Cài Nginx, curl, CA certificates, xz-utils, unzip, openssl bằng apt rồi dừng Nginx trước khi cấu hình. Không thay Python 3.10 hệ thống.

Tạo user `myhub` nếu chưa có; tạo `/opt/myhub`, `releases`, `incoming` với mode 755, owner myhub. Tạo `shared`, `shared/data`, `shared/bin`, `shared/python` với mode 700, owner myhub. Cài uv chính thức vào `shared/bin`, Python 3.13 vào `shared/python` bằng `UV_PYTHON_INSTALL_DIR`. Chạy uv từ `/opt/myhub` để không dò cấu hình ở `/root` khi chuyển user.

7-Zip/RAR: cài riêng bản Linux phù hợp nếu cần định dạng đó, đặt `SEVEN_ZIP_PATH`/`RAR_PATH` trong backend.env; đảm bảo giấy phép RAR. Nếu chưa cài, UI sẽ vô hiệu hóa định dạng tương ứng. ZIP/JAR/TAR/GZ/TGZ/ISO dùng thư viện Python đã khóa.

Nguồn uv: https://docs.astral.sh/uv/guides/install-python/

## 2. Cài cấu hình từ bộ setup đã rà soát (root)

Chuyển `data/myhub-vps-setup.zip` từ máy local bằng SCP vào VPS, giải nén ra `/root/myhub-setup`. Bộ zip này chỉ chứa mẫu/script triển khai và Mongo init; không chứa .env cá nhân hay nội dung data. Đường dẫn bên dưới giả định `deploy/` và `mongo-init/` nằm trong thư mục đó.

```bash
cd /root/myhub-setup
python3 deploy/init_config.py
install -d -m 755 /etc/myhub/mongo-init
install -m 600 deploy/compose.production.yml /etc/myhub/compose.production.yml
install -m 644 mongo-init/01-create-app-user.js /etc/myhub/mongo-init/01-create-app-user.js
install -d -m 700 /opt/myhub/shared/mongodb
install -m 755 deploy/release.sh /usr/local/bin/myhub-release
install -m 755 deploy/backup.sh /usr/local/bin/myhub-backup
install -m 644 deploy/myhub.service /etc/systemd/system/myhub.service
visudo -cf deploy/myhub-sudoers
install -m 440 deploy/myhub-sudoers /etc/sudoers.d/myhub
```

`init_config.py` chỉ dùng cho lần tạo database mới. Nó sinh khóa mới và mật khẩu hex cùng giá trị cho Mongo/app. Không chạy lại để chuyển VPS; khi chuyển máy phải mang cấu hình/khóa cũ.

Điền riêng bằng editor, không gửi nội dung vào chat:

```bash
nano /opt/myhub/shared/backend.env
```

Điền `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_DRIVE_ROOT_FOLDER_ID` (cùng root hiện tại), `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`. URL/CORS/cookie đã có mẫu production. Không đổi `MONGODB_URI`, `ENCRYPTION_KEY`, `JWT_SECRET_KEY` do script tạo nếu chưa có lý do cụ thể.

Google OAuth: thêm callbacks `https://myhub.liamcao.io.vn/api/v1/auth/google/callback` và `/api/v1/auth/drive/callback`. Giữ callback local nếu vẫn cần local. GitHub: dùng OAuth App production với callback `https://myhub.liamcao.io.vn/api/v1/auth/github/callback`. Cập nhật homepage theo hostname. Trong màn hình consent Google, kiểm tra trạng thái publishing: ứng dụng External ở Testing với Drive scope có thể hết hạn refresh token sau 7 ngày; chọn cấu hình publishing phù hợp trước khi dùng lâu dài.

Chạy DB mới và cài Nginx:

```bash
docker compose --env-file /etc/myhub/mongo.env -f /etc/myhub/compose.production.yml up -d --wait
install -m 644 deploy/nginx.conf /etc/nginx/sites-available/myhub
ln -s /etc/nginx/sites-available/myhub /etc/nginx/sites-enabled/myhub
# Chỉ bỏ symlink default của bản Nginx vừa cài; không xóa config ứng dụng khác.
unlink /etc/nginx/sites-enabled/default
nginx -t
systemctl daemon-reload
systemctl enable myhub.service nginx.service
systemctl start nginx.service
```

Chưa start backend trước khi có `current` release. Nginx trả 404/502 lúc chưa có bản phát hành là bình thường. Chỉ cổng 22 cần truy cập cho SSH; 8080/8000/27017 chỉ nghe localhost. Không thay firewall hoặc tắt SSH password trước khi đã kiểm tra đăng nhập key từ terminal thứ hai.

## 3. Route Cloudflare và OAuth

Trong tunnel `liamcao-vps`, thêm **Published application route**: hostname `myhub.liamcao.io.vn`, service HTTP `127.0.0.1:8080`. Dashboard tạo DNS CNAME đến tunnel. Không tạo A record về IP VPS cho hostname này. Route không dùng Cloudflare Access ở bước đầu vì MyHub đã có whitelist OAuth; Access cần cấu hình riêng nếu muốn thêm sau.

Không bật rule Cache Everything cho `/api/*`. Sau bản đầu, kiểm tra `https://myhub.liamcao.io.vn/api/v1/health` và đăng nhập/cấp Drive. Frontend/API cùng origin nên `VITE_API_BASE_URL=/api/v1`, cookie chỉ cần host hiện tại, không chia sẻ sang domain khác.

Tài liệu: https://developers.cloudflare.com/tunnel/concepts/routing/

## 4. SSH key và CI/CD

Trên máy cá nhân tạo key Ed25519 riêng cho CI; không ghi đè key có sẵn. Chỉ đưa public key vào `/home/myhub/.ssh/authorized_keys` (thư mục owner myhub mode 700, file 600). Dòng public key có thể dùng tiền tố `restrict` để tắt forwarding/PTY nhưng vẫn cho SCP/command deploy. Kiểm tra SSH key thành công trước khi dùng cho Actions. Giữ root SSH hiện tại làm đường quản trị; không dùng password root trong workflow.

Lấy host public key và fingerprint từ terminal VPS đang tin cậy:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
cat /etc/ssh/ssh_host_ed25519_key.pub
```

Tạo entry `known_hosts` bằng **IP hoặc hostname SSH thực tế**, ví dụ `<IP> ssh-ed25519 <PUBLIC_KEY>`. Cổng khác 22 dùng `[<IP>]:<PORT>`. Không lấy `ssh-keyscan` từ mạng rồi tin ngay mà không đối chiếu fingerprint.

Trong GitHub repo → Settings → Secrets and variables → Actions, thêm repository secrets:

| Secret | Giá trị |
|---|---|
| `DEPLOY_HOST` | IP/hostname SSH của VPS, không phải hostname tunnel web |
| `DEPLOY_PORT` | `22` |
| `DEPLOY_USER` | `myhub` |
| `DEPLOY_SSH_KEY` | Private key CI, không chứa passphrase; chỉ dùng riêng cho deploy |
| `DEPLOY_KNOWN_HOSTS` | Entry host key đã đối chiếu |

Secret ứng dụng vẫn ở VPS; Actions không cần Google/Drive/Mongo credentials. Repo private dùng repository secrets để không phụ thuộc tính năng GitHub Environment trả phí.

Workflow chạy CI trên PR và main. Merge hoặc push vào main tạo artifact chứa đúng source commit và frontend build. CD chỉ chạy khi repository **variable** `DEPLOY_ENABLED=true`. Giữ biến chưa bật trong bootstrap. Main cần giữ chính sách kiểm tra trước merge theo tính năng GitHub tài khoản hỗ trợ; workflow vẫn kiểm tra lại trước deploy kể cả push trực tiếp vào main.

Lần đầu: sau khi bootstrap, route, secrets hoàn tất, bật `DEPLOY_ENABLED=true`, rồi chạy **Run workflow** trên nhánh main. Hoặc tải artifact của lượt CI main đã thành công, chuyển `<SHA>.tar.gz` và `<SHA>.tar.gz.sha256` vào `/opt/myhub/incoming` (owner myhub), rồi root chạy `runuser -u myhub -- /usr/local/bin/myhub-release <SHA>`. Sau đó CI/CD hoàn toàn tự động với mỗi cập nhật main đã qua kiểm tra.

CI dùng Ubuntu 22.04, Python 3.13, Node 22, Edge headless; test Mongo/Drive giả lập không dùng bí mật production. Deploy dùng khóa ở Actions secrets, kiểm SSH host key, serialize bằng concurrency và flock. Bản main đã bị commit mới thay thế được bỏ qua. Script chỉ cần sudo quản lý service; không cho CI dùng root hoặc Docker.

Venv mỗi release được cài bằng requirements đã khóa. Deploy có thời gian restart ngắn, chưa phải zero downtime. Artifact không xóa release cũ, Mongo, shared/data hay env. Theo dõi dung lượng và chỉ dọn release không được current trỏ tới sau khi đã nghiệm thu; không chạy `docker compose down -v` để cập nhật code.

## 5. Kiểm tra sau lần triển khai đầu

- Health nội bộ Nginx và domain trả đúng mã commit release.
- Đăng nhập Google/GitHub; whitelist chỉ cho chủ tài khoản.
- Cấp quyền Drive, dùng root folder ID cũ: folder/file/Workspace lấy trực tiếp từ Drive, không cần copy nội dung lên VPS.
- Database mới không có thiết lập/thứ tự riêng của local; điều này là lựa chọn cho đợt chuyển đầu.
- Upload file hơn 100 MB rồi tải lại so checksum; thử mất mạng và chọn lại cùng file trong cùng tab sau reload để tiếp tục.
- Kiểm tra preview/PDF/video, archive và quyền thư mục tmp. Archive xử lý lâu có thể chạm timeout Cloudflare; chunk upload không giải quyết timeout của job archive. Nếu gặp cần tách job archive thành bất đồng bộ ở đợt riêng.
- Merge một thay đổi nhỏ để kiểm toàn luồng Actions → VPS. Chỉ xem CI/CD đã nghiệm thu sau bước này.

## 6. Upload qua Cloudflare Free

`services/upload.ts` chia file thành các request tối đa 8 MiB. `UploadService` kiểm scope, owner, độ dài và offset; Mongo `upload_sessions` lưu session URI mã hóa và tiến độ, có TTL 6 ngày. Drive nhận từng phần bằng resumable PUT. Giới hạn buffer ở VPS là từng phần, không ghi toàn bộ file vào đĩa.

Khi lỗi mạng, client backoff tối đa 5 lần rồi hỏi offset thật từ Drive. Nếu chưa hoàn tất, chọn lại cùng file trong cùng tab (kể cả sau reload) để tiếp tục; sessionStorage chỉ giữ ID phiên và fingerprint mẫu đầu/cuối, không giữ nội dung file/token. Đóng tab, clear storage hoặc hết hạn thì phiên có thể không tiếp tục được từ UI; đây chưa phải resume liên thiết bị. Nhấn Hủy thu hồi session app; dữ liệu chưa hoàn tất trên Google tự hết hạn. File hoàn tất đúng lúc hủy có thể đã xuất hiện và không bị xóa tự động.

URL upload của Drive không trả cho trình duyệt. JWT/phiên đăng nhập vẫn cần hợp lệ; app tự refresh token như trước. Không chạy nhiều backend workers/instances trong phiên bản này vì khóa ghi và upload hiện ở một process.

## 7. Backup và chuyển sang VPS khác

Chạy backup dưới user myhub:

```bash
runuser -u myhub -- /usr/local/bin/myhub-backup
```

Script khóa với deploy, dừng backend, xuất BSON Extended JSON gzip vào `shared/data/backups` rồi tải một bản vào folder hệ thống Drive, sau đó start lại backend dù upload backup lỗi. Gián đoạn web trong khoảng backup; CLI không sao lưu nội dung file Drive. Không có lịch backup tự động trong bộ này; chỉ thêm timer sau khi thống nhất lịch và thời gian gián đoạn.

Giữ thêm bản cấu hình và đặc biệt `ENCRYPTION_KEY` trong password manager/kho bí mật bên ngoài VPS. Bản backup database chứa credential Drive đã mã hóa nhưng không chứa khóa giải mã. Backup metadata không cứu được file Drive bị xóa vĩnh viễn; nếu cần phải có backup riêng cho nội dung Drive.

Chuyển VPS: chuẩn bị máy mới với cùng release và Mongo tương thích; chuyển backend.env (giữ khóa cũ, root ID và OAuth client), đặt password DB máy mới vào MONGODB_URI, chuyển file backup local. Dừng backend nguồn trong lần backup chốt; không để hai server cùng ghi trong lúc chuyển. Khi backend đích dừng, chạy trong release/backend của máy mới:

```bash
.venv/bin/python scripts/restore_db.py /duong-dan/backup.jsonl.gz --include-drive-credentials --confirm-replace
```

Sau restore, start backend và đăng nhập lại. Kiểm dữ liệu rồi chuyển route sang tunnel mới hoặc thay connector theo kế hoạch. Giữ máy cũ đến khi nghiệm thu. Không restore sessions/OAuth state/upload đang dở. Restore dùng staging và rename từng collection, không phải transaction toàn database; giữ backup máy đích trước ghi đè.

Chuyển về Windows local dùng cùng CLI với `.\.venv\Scripts\python.exe`, sửa URL/đường dẫn/cookie theo localhost, giữ encryption key nếu mang credential. Local phát triển nên dùng root Drive riêng sau khi production đi vào sử dụng để tránh sửa dữ liệu thật.

## 8. Rollback và giới hạn

Nếu restart hoặc health nội bộ thất bại, script đổi lại current và restart release trước; lần đầu chưa có release trước thì dừng service và báo lỗi. Không rollback dữ liệu tự động. Khi có migration database, phải thiết kế tương thích và backup trước khi áp dụng; không có lệnh reset database trong CD.

Nếu health public thất bại nhưng nội bộ đã đúng commit, Actions báo lỗi để kiểm tra DNS/tunnel/certificate; không tự rollback code tốt vì lỗi mạng ngoài. Nếu frontend đang mở sẵn, reload trang để nhận bundle mới; backend cập nhật sau deploy. Các bundle có hash để cache, index không cache.
