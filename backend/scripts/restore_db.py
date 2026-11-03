"""Khôi phục snapshot metadata từ local hoặc thư mục backup hệ thống trên Drive."""
import argparse
import asyncio
import gzip
import re
import uuid
from pathlib import Path
from bson import json_util
from _runtime import runtime

SKIPPED = {'refresh_sessions', 'oauth_states'}


def read_backup(path):
    """Validate JSONL gzip theo từng dòng, chặn tên collection tùy ý và input quá lớn."""
    total = 0
    with gzip.open(path, 'rt', encoding='utf-8') as source:
        header = json_util.loads(source.readline(1024 * 1024))
        if header.get('format') != 'myhub-backup' or header.get('version') != 1:
            raise ValueError('Định dạng backup không được hỗ trợ.')
        while line := source.readline(17 * 1024 * 1024):
            total += len(line.encode('utf-8'))
            if not line.endswith('\n') or total > 512 * 1024 * 1024:
                raise ValueError('Backup vượt giới hạn an toàn 512 MB hoặc document quá lớn.')
            item = json_util.loads(line)
            name = item.get('collection', '')
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,80}', name):
                raise ValueError('Tên collection không hợp lệ trong backup.')
            if 'document' in item and (not isinstance(item['document'], dict) or '_id' not in item['document']):
                raise ValueError('Document backup thiếu _id.')
            yield item


async def restore(arguments):
    """Tải backup nếu cần → validate toàn bộ → staging → đổi collection, không tự phục hồi phiên."""
    if not arguments.confirm_replace:
        raise ValueError('Cần --confirm-replace để xác nhận thay metadata hiện tại bằng backup. Dừng backend trước.')
    async with runtime() as (settings, mongo, drive, preview):
        if arguments.from_drive:
            system = await preview.system_folder()
            candidates = [f for f in await drive.children(system) if f['name'].startswith('backup-') and f['name'].endswith('.jsonl.gz')]
            if arguments.from_drive == 'latest':
                file = max(candidates, key=lambda f: f.get('createdTime', ''), default=None)
            else:
                file = next((f for f in candidates if f['id'] == arguments.from_drive), None)
            if not file:
                raise ValueError('Không tìm thấy backup trong thư mục hệ thống Drive.')
            directory = settings.local_data_dir / 'backups'
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f'restore-{uuid.uuid4().hex}.jsonl.gz'
            stream = await drive.stream(file['id'])
            downloaded = 0
            try:
                with path.open('wb') as output:
                    async for chunk in stream.content:
                        downloaded += len(chunk)
                        if downloaded > 256 * 1024 * 1024:
                            raise ValueError('Backup nén vượt giới hạn 256 MB.')
                        output.write(chunk)
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            finally:
                await stream.content.aclose()
        elif arguments.file:
            path = Path(arguments.file).resolve()
        else:
            raise ValueError('Chọn file local hoặc --from-drive latest/ID.')
        excluded = SKIPPED | (set() if arguments.include_drive_credentials else {'drive_credentials'})
        collections = {item['collection'] for item in read_backup(path) if item['collection'] not in excluded}
        stages = {name: f'_restore_{uuid.uuid4().hex}' for name in collections}
        try:
            for stage in stages.values():
                await mongo.create_collection(stage)
            for item in read_backup(path):
                if item['collection'] in stages and 'document' in item:
                    await mongo.stage_record(stages[item['collection']], item['document'])
            for name, stage in stages.items():
                await mongo.commit_stage(stage, name)
                print(f'Đã khôi phục collection: {name}')
            await mongo.revoke_sessions()
            await mongo.initialize()
        finally:
            for stage in stages.values():
                await mongo.drop_stage(stage)
        print('Hoàn tất. Phiên đăng nhập không được phục hồi; hãy đăng nhập lại.')


def parse_arguments():
    """CLI chỉ nhận tùy chọn rõ ràng, không nhận mật khẩu/token qua argv."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', nargs='?')
    parser.add_argument('--from-drive', metavar='latest|FILE_ID')
    parser.add_argument('--include-drive-credentials', action='store_true')
    parser.add_argument('--confirm-replace', action='store_true')
    arguments = parser.parse_args()
    if arguments.file and arguments.from_drive:
        parser.error('Chỉ chọn file local hoặc --from-drive.')
    return arguments


if __name__ == '__main__':
    # Không ghi đè tự động: người chạy phải chọn --confirm-replace rõ ràng.
    asyncio.run(restore(parse_arguments()))
