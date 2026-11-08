import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { useSession } from '../store/session';
import { deviceId } from './device';

export const API_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');
export const api = axios.create({ baseURL: API_URL, withCredentials: true });
let refreshPromise: Promise<string> | null = null;

// Xoay cookie một lần cho tất cả request đồng thời, tránh đua refresh token.
export async function refreshSession(): Promise<string> {
  if (!refreshPromise) {
    const rotate = () => axios.post(`${API_URL}/auth/refresh`, {}, { withCredentials: true });
    // Web Locks tuần tự hóa refresh giữa các tab cùng origin, cookie mới được đọc sau khi nhận khóa.
    const request = navigator.locks ? navigator.locks.request('myhub-refresh', rotate) : rotate();
    refreshPromise = request
      .then(({ data }) => {
        useSession.getState().set({ token: data.data.access_token, user: data.data.user });
        window.dispatchEvent(new Event('myhub:session-refreshed'));
        return data.data.access_token as string;
      }).finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

// Mọi API request đi qua adapter này; thêm Bearer từ bộ nhớ hiện tại.
api.interceptors.request.use((config) => {
  config.headers['X-MyHub-Device'] = deviceId;
  const token = useSession.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Request bị 401 chỉ refresh và retry một lần; hết phiên thì quay lại login.
api.interceptors.response.use((response) => response, async (error: AxiosError) => {
  const config = error.config as (InternalAxiosRequestConfig & { retried?: boolean }) | undefined;
  if (error.response?.status === 401 && config && !config.retried) {
    config.retried = true;
    try { config.headers.Authorization = `Bearer ${await refreshSession()}`; return api(config); }
    catch { useSession.getState().set({ user: null, token: null, workspace: null }); }
  }
  throw error;
});

// Đọc mã lỗi ổn định để i18n xử lý; lỗi không rõ không đưa stacktrace ra UI.
export function errorCode(error: unknown): string {
  return axios.isAxiosError(error) ? error.response?.data?.error?.code || 'network_error' : 'unknown_error';
}

// Cấp cookie phạm vi file → URL media/download dùng native streaming của browser.
export async function mediaUrl(workspaceId: string, fileId: string, action = 'content'): Promise<string> {
  await api.post(`/workspaces/${workspaceId}/files/${fileId}/access`);
  return `${API_URL}/workspaces/${workspaceId}/files/${fileId}/${action}`;
}

// Tải bằng trình duyệt, không gom toàn bộ file lớn thành Blob trong RAM.
export async function downloadFile(workspaceId: string, fileId: string, action = 'content') {
  const url = await mediaUrl(workspaceId, fileId, action);
  const anchor = document.createElement('a');
  anchor.href = url; anchor.target = '_blank'; anchor.rel = 'noopener noreferrer';
  document.body.append(anchor); anchor.click(); anchor.remove();
}
