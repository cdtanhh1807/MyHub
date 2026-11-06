#!/usr/bin/env bash
# Chạy dưới user myhub: giải nén bản đã kiểm tra → venv → switch → restart/rollback.
set -Eeuo pipefail
umask 022
base=/opt/myhub
sha=${1:?Usage: release.sh COMMIT_SHA}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid release SHA'; exit 2; }
[[ $(id -un) == myhub ]] || { echo 'Run as myhub'; exit 2; }
archive="$base/incoming/$sha.tar.gz"
release="$base/releases/$sha"
exec 9>"$base/shared/deploy.lock"
flock -n 9 || { echo 'Deployment/backup already running'; exit 1; }
[[ -f "$archive" && -f "$archive.sha256" && -f "$base/shared/backend.env" ]] || { echo 'Missing archive/checksum/config'; exit 1; }
cd "$base/incoming"
sha256sum --check "$sha.tar.gz.sha256"
export UV_PYTHON_INSTALL_DIR="$base/shared/python"
uv="$base/shared/bin/uv"
[[ -x "$uv" ]] || { echo 'uv not installed'; exit 1; }

# Bản cùng SHA đã tồn tại chỉ được dùng lại khi đã chuẩn bị hoàn tất, không sửa bản đang chạy.
if [[ ! -d "$release" ]]; then
    mkdir -m 755 "$release"
    "$uv" run --no-project --python 3.13 python - "$archive" "$release" <<'PY'
import sys, tarfile
# Python 3.13 data filter chặn symlink/path traversal thoát thư mục phát hành.
with tarfile.open(sys.argv[1]) as archive:
    archive.extractall(sys.argv[2], filter='data')
PY
    [[ $(cat "$release/RELEASE") == "$sha" && -f "$release/frontend/dist/index.html" ]] || { echo 'Invalid release'; exit 1; }
    ln -s "$base/shared/backend.env" "$release/backend/.env"
    "$uv" venv --python 3.13 "$release/backend/.venv"
    "$uv" pip install --python "$release/backend/.venv/bin/python" -r "$release/backend/requirements.txt"
    # Validate cấu hình trước khi dừng ứng dụng cũ, không in giá trị bí mật.
    (cd "$release/backend"; .venv/bin/python - <<'PY'
import sys
from app.config.settings import get_settings
# Không in exception validation vì có thể chứa giá trị cấu hình bí mật.
try:
    get_settings()
except Exception:
    print('Configuration invalid; inspect backend.env privately', file=sys.stderr)
    sys.exit(1)
print('Configuration valid')
PY
    )
    touch "$release/.ready"
fi
[[ -f "$release/.ready" ]] || { echo 'Incomplete release; inspect and remove this release directory before retrying'; exit 1; }
previous=$(readlink -f "$base/current" || true)
if [[ -n "$previous" && "$previous" != "$base/current" && "$previous" != "$base/releases/"* ]]; then
    echo 'Unexpected current symlink'; exit 1
fi

# Symlink chuyển nguyên tử; rollback chỉ code, không khôi phục ngược dữ liệu MongoDB.
switch_to() {
    ln -sfn "$1" "$base/.current-next"
    mv -Tf "$base/.current-next" "$base/current"
}
rollback() {
    trap - ERR
    if [[ -d "$previous" && -f "$previous/.ready" ]]; then
        switch_to "$previous"
        sudo -n /usr/bin/systemctl reset-failed myhub.service || true
        sudo -n /usr/bin/systemctl restart myhub.service || true
        echo "Deployment failed; restored previous release: $(basename "$previous")"
    else
        sudo -n /usr/bin/systemctl stop myhub.service || true
        echo 'First deployment failed; no previous release available'
    fi
    exit 1
}
trap rollback ERR
switch_to "$release"
sudo -n /usr/bin/systemctl reset-failed myhub.service
sudo -n /usr/bin/systemctl restart myhub.service
for attempt in $(seq 1 30); do
    if curl -fsS --max-time 3 http://127.0.0.1:8000/api/v1/health 2>/dev/null | "$release/backend/.venv/bin/python" -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("release")==sys.argv[1] and d.get("status")=="ok" else 1)' "$sha" 2>/dev/null; then
        # Xác minh cả Nginx đang phục vụ API và index mới trước khi báo thành công.
        curl -fsS --max-time 5 http://127.0.0.1:8080/api/v1/health > /dev/null
        curl -fsS --max-time 5 http://127.0.0.1:8080/ > /dev/null
        trap - ERR
        echo "Deployed $sha"
        exit 0
    fi
    sleep 2
done
false
