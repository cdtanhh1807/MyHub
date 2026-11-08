"""Kiểm thử archive thực, truyền luồng và quy tắc fallback chuyển đổi Office."""
import io
import os
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
import pycdlib
import httpx
import pytest
from app.core.errors import AppError
from app.dtos.contracts import FileRequest, FolderRequest
from app.repositories.drive import DriveRepository
from app.services.archive import ArchiveService


@pytest.mark.parametrize('fmt', ['zip', 'jar', 'tar', 'gz', 'tgz', 'iso'])
async def test_real_archive_and_temp_cleanup(container, settings, fmt):
    """Archive tạo được nội dung thật và tmp được dọn ngay khi stream kết thúc."""
    response = await container.archive.archive(FileRequest(workspace_id='ws', file_id='sub'), fmt)
    content = b''.join([chunk async for chunk in response.content])
    if fmt in ('zip', 'jar'):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            assert archive.read('hello.py') == b'hello'
    elif fmt in ('tar', 'gz', 'tgz'):
        with tarfile.open(fileobj=io.BytesIO(content), mode='r:*') as archive:
            assert archive.extractfile('hello.py').read() == b'hello'
    else:
        iso = pycdlib.PyCdlib()
        iso.open_fp(io.BytesIO(content))
        output = io.BytesIO()
        iso.get_file_from_iso_fp(output, rr_path='/hello.py')
        assert output.getvalue() == b'hello'
        iso.close()
    assert not list((settings.local_data_dir / 'tmp').iterdir())
    assert not container.archive.lock.locked()


async def test_archive_failure_and_scope_cleanup(container, settings):
    """Lỗi nguồn/đích không bỏ rác tmp và không giữ khóa archive vô hạn."""
    container.drive.files['text']['size'] = str(2 * 1024 * 1024)
    with pytest.raises(AppError, match='archive_space_limit'):
        await container.archive.archive(FileRequest(workspace_id='ws', file_id='sub'), 'zip')
    assert not container.archive.lock.locked()
    assert not list((settings.local_data_dir / 'tmp').iterdir())
    with pytest.raises(AppError, match='outside_workspace'):
        await container.archive.archive(FileRequest(workspace_id='ws', file_id='system'), 'zip')


async def test_archive_closed_before_first_byte(container, settings):
    """Client ngắt trước đọc body vẫn dọn được tmp và nhả khóa cho job tiếp theo."""
    response = await container.archive.archive(FileRequest(workspace_id='ws', file_id='sub'), 'zip')
    assert container.archive.lock.locked()
    await response.content.aclose()
    await response.content.aclose()
    assert not container.archive.lock.locked()
    assert not list((settings.local_data_dir / 'tmp').iterdir())


async def test_http_disconnect_releases_archive(container, settings):
    """Socket hỏng sau response.start vẫn đóng nguồn và xóa archive đang chờ tải."""
    from app.core.streaming import ManagedStreamingResponse
    from starlette.requests import ClientDisconnect
    dto = await container.archive.archive(FileRequest(workspace_id='ws', file_id='sub'), 'zip')

    async def receive():
        """ASGI receive không phải nguồn đóng kết nối trong tình huống test này."""
        return {'type': 'http.request'}

    async def send(message):
        """Giả lập mất socket trước byte body đầu tiên."""
        if message['type'] == 'http.response.body':
            raise OSError('Disconnected test socket')

    with pytest.raises(ClientDisconnect):
        await ManagedStreamingResponse(dto)({'type': 'http', 'asgi': {'spec_version': '2.4'}}, receive, send)
    assert not container.archive.lock.locked()
    assert not list((settings.local_data_dir / 'tmp').iterdir())


async def test_cancelled_scope_still_cleans_temp(container, settings):
    """AnyIO cancel scope không được hủy việc đóng handle và dọn archive."""
    import anyio
    dto = await container.archive.archive(FileRequest(workspace_id='ws', file_id='sub'), 'zip')
    with anyio.CancelScope() as scope:
        scope.cancel()
        await dto.content.aclose()
    assert not container.archive.lock.locked()
    assert not list((settings.local_data_dir / 'tmp').iterdir())


async def test_archive_missing_tools_and_safe_names(container, monkeypatch):
    """Không có CLI thì báo trước, tên Drive không được thoát thư mục tạm."""
    monkeypatch.setattr('shutil.which', lambda _: None)
    assert not container.archive.capabilities().data['rar']
    with pytest.raises(AppError, match='archive_tool_missing'):
        await container.archive.archive(FileRequest(workspace_id='ws', file_id='sub'), 'rar')
    for value in ['../evil', 'C:\\evil', 'CON', '..', 'a\x00b']:
        name = ArchiveService.safe_name(value)
        assert name and '/' not in name and '\\' not in name and '\x00' not in name and name != '..'


async def test_rar_cli_when_available(container, settings, tmp_path):
    """Dùng RAR có sẵn nếu được chỉ định; không cài phần mềm hoặc sửa cấu hình người dùng."""
    executable = os.environ.get('MYHUB_TEST_RAR_PATH') or shutil.which('rar')
    if not executable:
        pytest.skip('RAR CLI chưa có trong môi trường test')
    settings.rar_path = executable
    response = await container.archive.archive(FileRequest(workspace_id='ws', file_id='sub'), 'rar')
    path = tmp_path / 'verified.rar'
    path.write_bytes(b''.join([chunk async for chunk in response.content]))
    result = subprocess.run([executable, 'p', '-inul', str(path), 'hello.py'], capture_output=True, timeout=30,
        **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
    assert result.returncode == 0 and result.stdout == b'hello'


async def test_upload_stream_size_and_wrong_scope(container):
    """Byte stream quá size hoặc đích sai Workspace bị chặn trước khi hoàn tất upload."""
    from app.services.files import bytes_stream
    with pytest.raises(AppError, match='outside_workspace'):
        await container.files.upload(FolderRequest(workspace_id='ws', file_id='ws2', name='test.txt'), 'text/plain', 5, bytes_stream(b'hello'))
    assert not container.drive.calls
    with pytest.raises(AppError, match='upload_size_mismatch'):
        await container.files.upload(FolderRequest(workspace_id='ws', file_id='sub', name='test.txt'), 'text/plain', 4, bytes_stream(b'hello'))


async def test_editor_rejects_binary_and_large(container):
    """Không nhét nhị phân hoặc file lớn vào CodeMirror dù MIME giả là text."""
    container.drive.contents['text'] = b'abc\x00x'
    with pytest.raises(AppError, match='binary_or_non_utf8'):
        await container.files.text(FileRequest(workspace_id='ws', file_id='text'))
    container.drive.files['text']['size'] = str(10 * 1024 * 1024)
    with pytest.raises(AppError, match='editor_unavailable'):
        await container.files.text(FileRequest(workspace_id='ws', file_id='text'))


async def test_trash_filter_and_restore_order(container):
    """Không hiển thị trash ngoài root; không phục hồi con khi folder cha còn trashed."""
    for key in ('sub', 'text', 'other', 'external_file', 'ws2'):
        container.drive.files[key]['trashed'] = True
    result = await container.files.trash_list('ws')
    assert {file.id for file in result.files} == {'sub', 'text'}
    root = await container.files.trash_list()
    assert {file.id for file in root.files} == {'ws2', 'sub', 'text', 'other'}
    assert {file.id: file.workspace_id for file in root.files} == {'ws2': 'ws2', 'sub': 'ws', 'text': 'ws', 'other': 'ws2'}
    with pytest.raises(AppError, match='restore_parent_first'):
        await container.files.restore(FileRequest(workspace_id='ws', file_id='text'))
    await container.files.restore(FileRequest(workspace_id='ws', file_id='sub'))
    await container.files.restore(FileRequest(workspace_id='ws', file_id='text'))
    assert not container.drive.files['text']['trashed']


async def test_office_conversion_cleanup_on_export_failure(container, monkeypatch):
    """Lỗi export vẫn xóa vĩnh viễn đúng bản Google tạm, giữ file Office gốc."""
    container.drive.files['text'].update(name='document.docx', mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    original_stream = container.drive.stream

    async def fail_export(file_id, **kwargs):
        """Mô phỏng giới hạn export của Google để kiểm tra nhánh fallback."""
        if kwargs.get('export_mime'):
            raise AppError('drive_error_403', 403)
        return await original_stream(file_id, **kwargs)

    monkeypatch.setattr(container.drive, 'stream', fail_export)
    with pytest.raises(AppError, match='conversion_fallback'):
        await container.preview.office_pdf(FileRequest(workspace_id='ws', file_id='text'))
    deletions = [call for call in container.drive.calls if call[0] == 'delete_temporary']
    assert len(deletions) == 1 and deletions[0][1] != 'text'
    assert 'text' in container.drive.files


async def test_drive_repository_pagination_and_range(settings, container):
    """Adapter REST lấy hết pageToken và không làm mất Range/206 từ Google."""
    calls = []

    async def handler(request):
        """Transport giả HTTP, kiểm tra request thật mà repository tạo."""
        calls.append(request)
        if request.url.params.get('alt') == 'media':
            assert request.headers['range'] == 'bytes=1-2'
            return httpx.Response(206, content=b'el', headers={'Content-Range': 'bytes 1-2/5', 'Content-Length': '2'})
        if request.url.params.get('pageToken'):
            return httpx.Response(200, json={'files': [{'id': 'second'}]})
        return httpx.Response(200, json={'files': [{'id': 'first'}], 'nextPageToken': 'next'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        repo = DriveRepository(settings, container.mongo, http)
        repo._token, repo._expires = 'fake-access', 9999999999
        assert [f['id'] for f in await repo.children('ws')] == ['first', 'second']
        stream = await repo.stream('text', 'bytes=1-2')
        assert stream.status == 206 and stream.headers['content-range'] == 'bytes 1-2/5'
        assert b''.join([chunk async for chunk in stream.content]) == b'el'
