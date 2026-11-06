"""Sinh khóa/mật khẩu ngay trên VPS mới; không in bí mật và không ghi đè cấu hình cũ."""
import base64
import os
from pathlib import Path
import pwd
import secrets


def initialize():
    """Root tạo hai file riêng, quyền 600; giữ app password giống nhau giữa DB và backend."""
    if os.geteuid() != 0:
        raise SystemExit('Run as root on the VPS')
    account = pwd.getpwnam('myhub')
    shared = Path('/opt/myhub/shared')
    config = Path('/etc/myhub')
    config.mkdir(mode=0o700, exist_ok=True)
    target = shared / 'backend.env'
    database = config / 'mongo.env'
    if target.exists() or database.exists():
        raise SystemExit('Configuration already exists; no files changed. Do not regenerate production keys.')
    template_dir = Path(__file__).resolve().parent
    app_password = secrets.token_hex(32)
    backend = (template_dir / 'backend.env.example').read_text(encoding='utf-8')
    backend = backend.replace('JWT_SECRET_KEY=\n', f'JWT_SECRET_KEY={secrets.token_urlsafe(48)}\n')
    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    backend = backend.replace('ENCRYPTION_KEY=\n', f'ENCRYPTION_KEY={key}\n').replace('HEX_APP_PASSWORD', app_password)
    mongo = (template_dir / 'mongo.env.example').read_text(encoding='utf-8')
    mongo = mongo.replace('MONGO_ROOT_PASSWORD=\n', f'MONGO_ROOT_PASSWORD={secrets.token_hex(32)}\n')
    mongo = mongo.replace('MONGO_APP_PASSWORD=\n', f'MONGO_APP_PASSWORD={app_password}\n')
    # O_EXCL tránh thay khóa/mật khẩu khi chạy lại hoặc tiến trình khác tạo file cùng lúc.
    for path, content, owner in [(database, mongo, None), (target, backend, account)]:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as output:
            output.write(content)
        if owner:
            os.chown(path, owner.pw_uid, owner.pw_gid)
    print('Created backend.env and mongo.env. Fill OAuth and Drive root privately; never paste them into chat.')


if __name__ == '__main__':
    initialize()
