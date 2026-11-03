"""Bảo vệ phạm vi Drive dùng chung cho mọi feature, kể cả restore/archive."""
from app.core.errors import AppError
from app.utils.files import FOLDER, drive_id


class ScopeService:
    """Không tin workspace/file/parent ID do trình duyệt gửi lên."""
    def __init__(self, settings, drive):
        """Gắn root cấu hình và nguồn metadata Drive."""
        self.settings, self.drive = settings, drive

    def system(self, file):
        """Ẩn/chặn folder hệ thống theo marker và tên dự phòng ở root."""
        return file.get('appProperties', {}).get('myhubSystem') == 'true' or (
            self.settings.google_drive_root_folder_id in file.get('parents', []) and file['name'] == self.settings.drive_system_folder_name)

    async def workspace(self, workspace_id, allow_trashed=False):
        """Workspace phải là con trực tiếp root, dạng folder và không thuộc hệ thống."""
        file = await self.drive.get(drive_id(workspace_id))
        if (file['mimeType'] != FOLDER or self.settings.google_drive_root_folder_id not in file.get('parents', [])
                or self.system(file) or (file.get('trashed') and not allow_trashed)):
            raise AppError('outside_workspace', 403)
        return file

    async def file(self, workspace_id, file_id, allow_trashed=False):
        """Lần theo toàn bộ chuỗi cha đến Workspace; chặn cycle, shortcut và root lạc phạm vi."""
        workspace = await self.workspace(workspace_id, allow_trashed)
        current = await self.drive.get(drive_id(file_id))
        original, path, seen = current, [], set()
        for _ in range(128):
            if current['id'] == self.settings.google_drive_root_folder_id:
                break
            if current['id'] in seen or self.system(current) or (current.get('trashed') and not allow_trashed):
                break
            if current['mimeType'] == 'application/vnd.google-apps.shortcut':
                raise AppError('shortcut_not_supported', 422)
            seen.add(current['id'])
            path.append(current)
            if current['id'] == workspace['id']:
                return original, list(reversed(path))
            parents = current.get('parents', [])
            if len(parents) != 1 or parents[0] == self.settings.google_drive_root_folder_id:
                break
            try:
                current = await self.drive.get(drive_id(parents[0]))
            except AppError as error:
                if error.status in (403, 404):
                    break
                raise
        raise AppError('outside_workspace', 403)

    async def folder(self, workspace_id, file_id):
        """Áp dụng scope trước, sau đó đảm bảo đối tượng là thư mục."""
        file, path = await self.file(workspace_id, file_id)
        if file['mimeType'] != FOLDER:
            raise AppError('not_a_folder', 422)
        return file, path

    async def descendants(self, folder_id):
        """Duyệt cây không đệ quy Python; bỏ system/shortcut, chặn số mục quá lớn."""
        queue, seen, result = [folder_id], set(), []
        while queue:
            parent = queue.pop()
            if parent in seen:
                raise AppError('folder_cycle', 409)
            seen.add(parent)
            for child in await self.drive.children(parent):
                if self.system(child):
                    continue
                if child['mimeType'] == 'application/vnd.google-apps.shortcut':
                    raise AppError('shortcut_not_supported', 422)
                result.append(child)
                if len(result) > self.settings.archive_max_files:
                    raise AppError('too_many_files', 413)
                if child['mimeType'] == FOLDER:
                    queue.append(child['id'])
        return result
