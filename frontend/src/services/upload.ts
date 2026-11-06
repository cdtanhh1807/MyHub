import axios from 'axios';
import { api, API_URL } from './api';
import { useSession } from '../store/session';

interface UploadState {
  upload_id: string; offset: number; size: number; chunk_size: number; complete: boolean;
}

// Lưu ID phiên theo file/đích/người dùng; không lưu file, URL Google hoặc token vào storage.
function checkpoint(key: string, value?: string | null): string | null {
  try {
    if (value === null) sessionStorage.removeItem(key);
    else if (value !== undefined) sessionStorage.setItem(key, value);
    return sessionStorage.getItem(key);
  } catch { return null; }
}

// Hash phần đầu/cuối giới hạn 256 KiB để nhận lại file khi người dùng chọn sau reload.
async function fileKey(file: File, workspace: string, parent: string): Promise<string> {
  const sample = new Blob([file.slice(0, 128 * 1024), file.slice(Math.max(0, file.size - 128 * 1024))]);
  const hash = await crypto.subtle.digest('SHA-256', await sample.arrayBuffer());
  const digest = Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('');
  return `myhub.upload:${JSON.stringify([API_URL, useSession.getState().user?.id, workspace, parent, file.name, file.size, file.lastModified, digest])}`;
}

// Backoff hủy được ngay, không giữ listener sau khi timeout hoặc nhấn Hủy.
function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); reject(new axios.CanceledError()); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
  });
}

// Tải tuần tự từng phần tối đa 8 MiB; sau lỗi hỏi offset Drive qua backend trước khi gửi tiếp.
export async function uploadFile(file: File, workspace: string, parent: string, signal: AbortSignal, progress: (percent: number) => void) {
  const root = `/workspaces/${workspace}/uploads`;
  const key = await fileKey(file, workspace, parent);
  let id = checkpoint(key);
  let state: UploadState | undefined;
  try {
    signal.throwIfAborted();
    if (id) {
      try { state = (await api.get(`${root}/${id}`, { signal })).data.data; }
      catch (error) {
        if (!axios.isAxiosError(error) || ![404, 410].includes(error.response?.status || 0)) throw error;
        checkpoint(key, null); id = null;
      }
    }
    if (!state) {
      state = (await api.post(root, { parent_id: parent, name: file.name, size: file.size, mime: file.type || 'application/octet-stream' }, { signal })).data.data as UploadState;
      id = state.upload_id;
      checkpoint(key, id);
    }
    let failures = 0;
    let reconcile = false;
    while (!state.complete) {
      signal.throwIfAborted();
      try {
        if (reconcile) {
          state = (await api.get(`${root}/${id}`, { signal })).data.data as UploadState;
          reconcile = false;
          if (state.complete) break;
        }
        if (state.size !== file.size || state.chunk_size <= 0 || state.chunk_size > 8 * 1024 * 1024 || state.offset < 0 || state.offset > file.size) throw new Error('Invalid upload state');
        const offset = state.offset;
        const chunk = file.slice(offset, offset + state.chunk_size);
        const before = offset;
        const response = await api.put(`${root}/${id}`, chunk, { params: { offset }, signal, timeout: 120_000,
          headers: { 'Content-Type': 'application/octet-stream' }, onUploadProgress: event => {
            progress(Math.min(99, Math.floor(100 * (offset + event.loaded) / (file.size || 1))));
          } });
        state = response.data.data as UploadState;
        if (!state.complete && state.offset <= before) throw new axios.AxiosError('Upload stalled', 'ERR_NETWORK');
        progress(Math.min(99, Math.floor(100 * state.offset / (file.size || 1))));
        failures = 0;
      } catch (error) {
        if (signal.aborted || !axios.isAxiosError(error)) throw error;
        const status = error.response?.status;
        if (status && ![409, 429, 500, 502, 503, 504].includes(status)) throw error;
        if (++failures > 5) throw error;
        await wait(Math.min(1000 * 2 ** (failures - 1), 15000), signal);
        reconcile = true;
      }
    }
    checkpoint(key, null);
    progress(100);
  } catch (error) {
    if (signal.aborted) {
      checkpoint(key, null);
      if (id) await api.delete(`${root}/${id}`, { timeout: 10000 }).catch(() => {});
      throw new axios.CanceledError();
    }
    // Giữ checkpoint khi hết retry để chọn lại cùng file có thể tiếp tục phiên còn hạn.
    throw error;
  }
}
