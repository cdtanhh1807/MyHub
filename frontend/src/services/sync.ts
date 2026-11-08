import type { QueryClient, QueryKey } from '@tanstack/react-query';

export interface Change {
  kind: 'files' | 'workspaces' | 'preferences' | 'connection' | 'reset';
  workspace_ids: string[]; parent_ids: string[]; file_ids: string[]; tree: boolean; trash: boolean;
}
export interface SyncMessage { event: string; cursor: string; changes: Change[] }

// Parser SSE nhận được UTF-8 chia tùy ý theo TCP chunk; có giới hạn bộ nhớ và không eval dữ liệu.
export async function readEventStream(body: ReadableStream<Uint8Array>, signal: AbortSignal, receive: (message: SyncMessage) => void, activity: () => void) {
  const reader = body.getReader();
  const abort = () => { void reader.cancel().catch(() => {}); };
  signal.addEventListener('abort', abort, { once: true });
  const decoder = new TextDecoder();
  let buffer = '', event = '', cursor = '', data: string[] = [], size = 0;
  function line(value: string) {
    // Một blank line kết thúc frame; heartbeat comment không tạo invalidation.
    if (!value) {
      if (data.length) {
        const parsed = JSON.parse(data.join('\n')) as { changes?: unknown };
        const changes = Array.isArray(parsed.changes) ? parsed.changes : [];
        if (changes.length > 256) throw new Error('Invalid sync batch');
        for (const item of changes) {
          if (!item || !['files', 'workspaces', 'preferences', 'connection', 'reset'].includes(item.kind)
              || !['workspace_ids', 'parent_ids', 'file_ids'].every(key => Array.isArray(item[key]) && item[key].length <= 100 && item[key].every((id: unknown) => typeof id === 'string' && id.length <= 200))) throw new Error('Invalid sync event');
        }
        receive({ event: event || 'message', cursor, changes });
      }
      event = ''; cursor = ''; data = []; size = 0; return;
    }
    if (value.startsWith(':')) return;
    const index = value.indexOf(':');
    const field = index < 0 ? value : value.slice(0, index);
    const content = index < 0 ? '' : value.slice(index + 1).replace(/^ /, '');
    if (field === 'event') event = content;
    if (field === 'id' && /^[a-f0-9]{32}:\d{1,20}$/.test(content)) cursor = content;
    if (field === 'data') { data.push(content); size += content.length; }
    if (size > 512 * 1024) throw new Error('Sync frame too large');
  }
  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) break;
      activity(); buffer += decoder.decode(value, { stream: true });
      if (buffer.length > 1024 * 1024) throw new Error('Sync buffer too large');
      let match: RegExpExecArray | null;
      while ((match = /\r\n|\r|\n/.exec(buffer))) {
        // CR ở cuối chunk có thể là nửa đầu của CRLF, chờ chunk tiếp theo.
        if (match[0] === '\r' && match.index === buffer.length - 1) break;
        line(buffer.slice(0, match.index)); buffer = buffer.slice(match.index + match[0].length);
      }
    }
  } finally { signal.removeEventListener('abort', abort); await reader.cancel().catch(() => {}); reader.releaseLock(); }
}

// Chỉ cache thuộc phạm vi thay đổi mới cần đọc lại; editor tự xử lý version/bản nháp từ metadata.
export function affected(key: QueryKey, change: Change): boolean {
  const type = String(key[0]);
  if (type === 'office-pdf' || type === 'archive-formats') return false;
  if (change.kind === 'reset' || change.kind === 'connection') return true;
  if (change.kind === 'preferences') return type === 'settings' || type === 'workspaces';
  if (type === 'workspaces') return change.kind === 'workspaces';
  if (type === 'trash') return change.trash || change.kind === 'workspaces';
  const inWorkspace = change.workspace_ids.includes(String(key[1]));
  if (type === 'files' || type === 'destination') return inWorkspace && (change.tree || !change.parent_ids.length || change.parent_ids.includes(String(key[2])));
  if (type === 'metadata' || type === 'viewer') return change.file_ids.includes(String(key[2])) || (change.tree && inWorkspace);
  if (type === 'permissions' || type === 'revisions') return change.file_ids.includes(String(key[1])) || change.tree;
  if (type === 'impact') return inWorkspace;
  return false;
}

export const resetChange: Change = { kind: 'reset', workspace_ids: [], parent_ids: [], file_ids: [], tree: true, trash: true };

// Một batch nhiều file chỉ invalidation một lần; tab nền chỉ đánh dấu stale, không tự gọi Drive.
export function applyChanges(client: QueryClient, changes: Change[]) {
  if (!changes.length) return;
  void client.invalidateQueries({ predicate: query => changes.some(change => affected(query.queryKey, change)),
    refetchType: document.visibilityState === 'hidden' ? 'none' : 'active' });
}
