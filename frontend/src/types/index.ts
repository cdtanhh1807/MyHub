// Hợp đồng metadata tương ứng FileDTO phía backend; file gốc không nằm trong DB.
export interface DriveFile {
  id: string; name: string; mimeType: string; size?: string | null;
  createdTime?: string; modifiedTime?: string; version?: string; webViewLink?: string;
  parents: string[]; trashed?: boolean; permissions: Permission[];
  workspace_id?: string; workspace_name?: string;
}
export interface Permission { id: string; type: string; role: string; emailAddress?: string; displayName?: string }
export interface User { id: string; provider: string; name: string; identity: string; avatar?: string }
export interface Preferences {
  language: 'vi' | 'en'; theme: 'light' | 'dark' | 'system'; view: 'grid' | 'list';
  workspace_sort: 'name' | 'date' | 'manual'; direction: 'asc' | 'desc';
}
export interface FileList { files: DriveFile[]; breadcrumbs: DriveFile[] }
export const FOLDER = 'application/vnd.google-apps.folder';
