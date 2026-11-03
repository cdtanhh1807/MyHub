"""Đóng gói folder bằng workspace tạm riêng, không giải nén file người dùng."""
import asyncio
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path
import pycdlib
from app.core.errors import AppError
from app.dtos.contracts import ResultDTO, StreamDTO
from app.services.files import NATIVE_EXPORTS
from app.services.preview import local_chunks
from app.utils.files import FOLDER, disposition

FORMATS = ('zip', 'rar', '7z', 'tar', 'gz', 'tgz', 'jar', 'iso')


class ArchiveService:
    """Một job tại một thời điểm; dữ liệu tạm được giới hạn và xóa khi lỗi/hủy/kết thúc."""
    def __init__(self, settings, drive, scope):
        """Gắn adapter và khóa chống nhiều job cùng làm đầy đĩa."""
        self.settings, self.drive, self.scope = settings, drive, scope
        self.lock = asyncio.Lock()

    def capabilities(self):
        """Kiểm tra công cụ hiện có, UI chỉ cho chọn định dạng sẵn sàng."""
        available = {fmt: True for fmt in FORMATS}
        available['7z'] = bool(shutil.which(self.settings.seven_zip_path))
        available['rar'] = bool(shutil.which(self.settings.rar_path))
        return ResultDTO(data=available)

    @staticmethod
    def safe_name(value):
        """Chuẩn hóa tên Drive thành một path component an toàn trên Windows/Ubuntu."""
        value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip('. ')[:140] or 'unnamed'
        if value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
            value = '_' + value
        return value

    async def archive(self, request, fmt):
        """Validate cây trước → stream từng file xuống tmp → đóng gói → stream và dọn."""
        if fmt not in FORMATS:
            raise AppError('unsupported_archive')
        if not self.capabilities().data[fmt]:
            raise AppError('archive_tool_missing', 503)
        await self.scope.folder(request.workspace_id, request.file_id)
        if self.lock.locked():
            raise AppError('archive_busy', 409)
        await self.lock.acquire()
        temporary = None
        try:
            tmp_root = self.settings.local_data_dir / 'tmp'
            tmp_root.mkdir(parents=True, exist_ok=True)
            temporary = tempfile.TemporaryDirectory(prefix='archive-', dir=tmp_root)
            base = Path(temporary.name)
            source = base / 'contents'
            source.mkdir()
            items = await self.scope.descendants(request.file_id)
            maximum = self.settings.archive_max_mb * 1024 * 1024
            if sum(int(f.get('size') or 0) for f in items) > maximum or shutil.disk_usage(base).free < maximum * 2:
                raise AppError('archive_space_limit', 413)
            paths, used, total = {request.file_id: source}, set(), 0
            # descendants trả cha trước con, nên có thể dựng cây theo thứ tự này.
            for file in items:
                parent = paths.get(file.get('parents', [''])[0])
                if parent is None:
                    raise AppError('folder_changed', 409)
                mime, suffix = NATIVE_EXPORTS.get(file['mimeType'], (None, ''))
                name = self.safe_name(file['name'] + suffix)
                original_name, sequence = name, 1
                while (str(parent), name.casefold()) in used:
                    sequence += 1
                    name = f'{sequence}-{file["id"][:12]}-{original_name}'
                used.add((str(parent), name.casefold()))
                target = parent / name
                if not target.resolve().is_relative_to(source.resolve()):
                    raise AppError('invalid_archive_path', 403)
                if file['mimeType'] == FOLDER:
                    target.mkdir()
                    paths[file['id']] = target
                else:
                    # Scope kiểm tra lại ngay trước tải, phòng file vừa bị di chuyển ra khỏi cây.
                    await self.scope.file(request.workspace_id, file['id'])
                    stream = await self.drive.stream(file['id'], export_mime=mime)
                    try:
                        with target.open('wb') as output:
                            async for chunk in stream.content:
                                total += len(chunk)
                                if total > maximum:
                                    raise AppError('archive_space_limit', 413)
                                await asyncio.to_thread(output.write, chunk)
                    finally:
                        await stream.content.aclose()
            output = base / f'download.{fmt}'
            if fmt in ('7z', 'rar'):
                await self.pack_cli(source, output, fmt)
            else:
                await asyncio.to_thread(self.pack_python, source, output, fmt)
            if output.stat().st_size > maximum:
                raise AppError('archive_space_limit', 413)
            folder, _ = await self.scope.folder(request.workspace_id, request.file_id)

            def cleanup():
                """Giữ TemporaryDirectory sống đến cuối stream rồi giải phóng khóa job."""
                temporary.cleanup()
                self.lock.release()

            return StreamDTO(content=local_chunks(output, cleanup), headers={'Content-Type': 'application/octet-stream',
                'Content-Length': str(output.stat().st_size), 'Content-Disposition': disposition(folder['name'] + '.' + fmt), 'Cache-Control': 'private, no-store'})
        except BaseException:
            if temporary:
                temporary.cleanup()
            self.lock.release()
            raise

    async def pack_cli(self, source, output, fmt):
        """Dùng argv, không shell; chỉ truyền đường dẫn app tạo, chặn option injection."""
        executable = shutil.which(self.settings.seven_zip_path if fmt == '7z' else self.settings.rar_path)
        command = [executable, 'a', '-t7z', '-mx=5', str(output), '.'] if fmt == '7z' else [executable, 'a', '-r', '-ep1', str(output), '.']
        process = await asyncio.create_subprocess_exec(*command, cwd=source, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
        try:
            await asyncio.wait_for(process.wait(), timeout=self.settings.archive_timeout_seconds)
            if process.returncode != 0:
                raise AppError('archive_failed', 502)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise

    @staticmethod
    def pack_python(source, output, fmt):
        """ZIP/JAR/TAR/GZIP dùng stdlib; ISO9660 có Joliet + Rock Ridge giữ tên Unicode."""
        if fmt in ('zip', 'jar'):
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for path in sorted(source.rglob('*')):
                    archive.write(path, path.relative_to(source).as_posix())
        elif fmt in ('tar', 'gz', 'tgz'):
            with tarfile.open(output, 'w' if fmt == 'tar' else 'w:gz') as archive:
                for path in source.iterdir():
                    archive.add(path, arcname=path.name)
        elif fmt == 'iso':
            iso = pycdlib.PyCdlib()
            iso.new(interchange_level=3, joliet=3, rock_ridge='1.09', vol_ident='MYHUB')
            mapping, joliet_mapping = {source: ''}, {source: ''}
            try:
                for index, path in enumerate(sorted(source.rglob('*'), key=lambda p: (len(p.parts), str(p))), start=1):
                    iso_path = mapping[path.parent] + f'/N{index:07d}'
                    # Joliet giới hạn component; Rock Ridge vẫn giữ tên đầy đủ.
                    joliet = joliet_mapping[path.parent] + '/' + path.name[:24] + f'_{index}'
                    if path.is_dir():
                        iso.add_directory(iso_path=iso_path, rr_name=path.name, joliet_path=joliet)
                        mapping[path] = iso_path
                        joliet_mapping[path] = joliet
                    else:
                        iso.add_file(str(path), iso_path=iso_path + ';1', rr_name=path.name, joliet_path=joliet)
                iso.write(str(output))
            finally:
                iso.close()
