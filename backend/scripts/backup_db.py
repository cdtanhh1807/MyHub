"""Sao lưu toàn bộ collection thành BSON Extended JSONL gzip, lưu local và Drive."""
import asyncio
import gzip
from datetime import datetime, timezone
from bson import json_util
from _runtime import runtime
from app.services.preview import local_chunks


async def backup():
    """Stream document → gzip local → upload vào folder hệ thống; không sao chép file Drive."""
    async with runtime() as (settings, mongo, drive, preview):
        directory = settings.local_data_dir / 'backups'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'backup-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.jsonl.gz'
        partial = path.with_suffix('.part')
        try:
            with gzip.open(partial, 'wt', encoding='utf-8', newline='\n') as output:
                output.write(json_util.dumps({'format': 'myhub-backup', 'version': 1, 'created_at': datetime.now(timezone.utc)}) + '\n')
                for collection in sorted(await mongo.collection_names()):
                    if collection.startswith('_restore_') or collection in {'sync_log', 'drive_sync_state', 'drive_sync_index'}:
                        continue
                    output.write(json_util.dumps({'collection': collection}) + '\n')
                    async for record in mongo.records(collection):
                        output.write(json_util.dumps({'collection': collection, 'document': record}) + '\n')
            partial.replace(path)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        print(f'Đã tạo backup cục bộ: {path}')
        system = await preview.system_folder()
        stream = local_chunks(path)
        try:
            uploaded = await drive.upload(system, path.name, 'application/gzip', path.stat().st_size, stream)
        finally:
            await stream.aclose()
        print(f'Đã tải backup lên Drive, ID: {uploaded["id"]}')


if __name__ == '__main__':
    # Người dùng tự chạy script sau khi MongoDB hoạt động và Drive đã được cấp quyền.
    asyncio.run(backup())
