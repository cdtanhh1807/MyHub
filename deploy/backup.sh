#!/usr/bin/env bash
# Backup nhất quán: dừng backend ngắn, chạy CLI, rồi bật lại dù CLI lỗi upload Drive.
set -Eeuo pipefail
umask 077
[[ $(id -un) == myhub ]] || { echo 'Run as myhub'; exit 2; }
exec 9>/opt/myhub/shared/deploy.lock
flock -n 9 || { echo 'Deployment/backup already running'; exit 1; }
cd /opt/myhub/current/backend
restart() { sudo -n /usr/bin/systemctl start myhub.service; }
sudo -n /usr/bin/systemctl stop myhub.service
trap restart EXIT
.venv/bin/python scripts/backup_db.py
