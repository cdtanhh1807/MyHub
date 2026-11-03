"""Backup dùng BSON Extended JSON: giữ kiểu dữ liệu và từ chối input không hợp lệ."""
import gzip
import sys
from datetime import datetime, timezone
from pathlib import Path
from bson import ObjectId, json_util
import pytest

# Import parser CLI không mở kết nối Mongo/Drive hay đọc env thực.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from restore_db import read_backup


def test_backup_parser_bson_roundtrip(tmp_path):
    """Datetime và ObjectId không bị đổi thành chuỗi thông thường sau restore parse."""
    record = {'_id': ObjectId(), 'created': datetime(2026, 11, 3, 0, 0, tzinfo=timezone.utc)}
    path = tmp_path / 'backup.gz'
    with gzip.open(path, 'wt', encoding='utf-8') as output:
        for item in [{'format': 'myhub-backup', 'version': 1}, {'collection': 'users'}, {'collection': 'users', 'document': record}]:
            output.write(json_util.dumps(item) + '\n')
    result = list(read_backup(path))
    assert result[1]['document']['_id'] == record['_id']
    assert isinstance(result[1]['document']['created'], datetime)


@pytest.mark.parametrize('collection', ['system.users', '$cmd', '../evil', '_restore_evil'])
def test_backup_parser_rejects_unsafe_collection(tmp_path, collection):
    """Không cho backup điều khiển namespace Mongo đặc biệt hoặc staging nội bộ."""
    path = tmp_path / 'invalid.gz'
    with gzip.open(path, 'wt', encoding='utf-8') as output:
        output.write(json_util.dumps({'format': 'myhub-backup', 'version': 1}) + '\n')
        output.write(json_util.dumps({'collection': collection}) + '\n')
    with pytest.raises(ValueError):
        list(read_backup(path))
