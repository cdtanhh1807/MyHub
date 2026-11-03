#!/usr/bin/env bash
# Chạy trong WSL2/Ubuntu: đọc env như dữ liệu, xác nhận đúng đường dẫn rồi mới dọn.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd -- "$project_dir"
if [[ ! -f .env ]]; then
  echo 'Không có .env ở gốc. Không có dữ liệu nào bị xóa.' >&2
  exit 1
fi
data_path="$(python3 -c 'from pathlib import Path; lines=Path(".env").read_text().splitlines(); values=[s.split("=",1)[1].strip().strip(chr(34)).strip(chr(39)) for s in lines if s.strip().startswith("MONGO_DATA_DIR=")]; print(values[-1] if values else "")')"
resolved_path="$(realpath -e -- "$data_path")"
# Chỉ cho xóa một thư mục đích tên mongodb trong home; chặn root, home và ổ Windows.
if [[ "$data_path" != /* || "$resolved_path" != /home/*/myhub-data/mongodb || -L "$data_path" ]]; then
  echo "Từ chối xóa đường dẫn ngoài mẫu /home/<user>/myhub-data/mongodb: $resolved_path" >&2
  echo 'Nếu bạn dùng vị trí tùy chỉnh, hãy docker compose down --rmi all rồi tự kiểm tra và xóa thư mục.' >&2
  exit 1
fi
echo "Sẽ dừng MongoDB MyHub, xóa image Compose và xóa TOÀN BỘ: $resolved_path"
read -r -p 'Nhập đường dẫn đầy đủ bên trên để xác nhận: ' confirmation
if [[ "$confirmation" != "$resolved_path" ]]; then
  echo 'Đã hủy.'
  exit 1
fi
docker compose down --rmi all
# Sau xác nhận, vẫn kiểm tra lại realpath để tránh thay mục tiêu giữa hai bước.
[[ "$(realpath -e -- "$data_path")" == "$resolved_path" && ! -L "$data_path" ]]
if [[ -w "$resolved_path" ]]; then
  rm -rf -- "$resolved_path"
else
  sudo rm -rf -- "$resolved_path"
fi
echo 'Đã dọn MongoDB của MyHub. File trên Google Drive không bị tác động.'
