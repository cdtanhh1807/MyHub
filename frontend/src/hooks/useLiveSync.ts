import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, API_URL, refreshSession } from '../services/api';
import { useSession } from '../store/session';
import { deviceId } from '../services/device';
import { applyChanges, readEventStream, resetChange, type Change, type SyncMessage } from '../services/sync';

// SSE có Bearer; Web Locks/BroadcastChannel chia sẻ một kết nối giữa các tab đang hiển thị.
export function useLiveSync() {
  const userId = useSession(state => state.user?.id);
  const client = useQueryClient();
  useEffect(() => {
    if (!userId) return;
    const name = `myhub.sync:${API_URL}:${userId}`;
    const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(name) : null;
    let cursor = sessionStorage.getItem(name) || '';
    if (!/^[a-f0-9]{32}:\d{1,20}$/.test(cursor)) cursor = '';
    let controller: AbortController | null = null;
    let pending: Change[] = [], flush: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;
    function receive(message: SyncMessage, broadcast = false) {
      // Cursor công khai được lưu riêng mỗi tab, token không đi qua storage hoặc BroadcastChannel.
      if (message.cursor) {
        const [epoch, sequence] = message.cursor.split(':');
        const [previousEpoch, previousSequence] = cursor.split(':');
        if (message.event !== 'reset' && epoch === previousEpoch && BigInt(sequence) < BigInt(previousSequence)) return;
        cursor = message.cursor; sessionStorage.setItem(name, cursor);
      }
      if (message.event === 'reset') pending = [resetChange];
      else if (message.event === 'changes') pending.push(...message.changes);
      if (pending.length > 256) pending = [resetChange];
      if (pending.length && !flush) flush = setTimeout(() => { const changes = pending; pending = []; flush = undefined; applyChanges(client, changes); }, 200);
      if (broadcast) channel?.postMessage(message);
    }
    if (channel) channel.onmessage = event => receive(event.data as SyncMessage);
    async function pause(ms: number, signal: AbortSignal) {
      // Mọi timer đều hủy được để tab đóng/đăng xuất không để lại kết nối hoặc retry ngầm.
      if (signal.aborted) return;
      await new Promise<void>(resolve => {
        const done = () => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve(); };
        const timer = setTimeout(done, ms); signal.addEventListener('abort', done, { once: true });
      });
    }
    async function connect(signal: AbortSignal) {
      let failures = 0, lastFallback = 0, fallbackRevision = '';
      while (!signal.aborted && !disposed) {
        const connection = new AbortController();
        const abort = () => connection.abort();
        signal.addEventListener('abort', abort, { once: true });
        window.addEventListener('myhub:session-refreshed', abort);
        let watchdog: ReturnType<typeof setTimeout> | undefined;
        let refresh = false;
        const opened = Date.now();
        const token = useSession.getState().token;
        const activity = () => { clearTimeout(watchdog); watchdog = setTimeout(abort, 70000); };
        try {
          activity();
          const response = await fetch(`${API_URL}/sync/events`, { credentials: 'include', signal: connection.signal,
            headers: { Authorization: `Bearer ${token || ''}`, Accept: 'text/event-stream', 'X-MyHub-Device': deviceId, ...(cursor ? { 'Last-Event-ID': cursor } : {}) } });
          if (response.status === 401) { refresh = true; throw new Error('Sync authentication expired'); }
          if (!response.ok || !response.body || !response.headers.get('content-type')?.startsWith('text/event-stream')) throw new Error('Sync stream unavailable');
          await readEventStream(response.body, connection.signal, message => {
            if (message.event === 'auth_expired') { refresh = true; connection.abort(); return; }
            receive(message, true);
          }, activity);
        } catch {
          // Lỗi stream được xử lý ở đây; lỗi phiên dùng chung luồng refresh đã chống race giữa các tab.
        } finally {
          clearTimeout(watchdog); connection.abort(); signal.removeEventListener('abort', abort);
          window.removeEventListener('myhub:session-refreshed', abort);
        }
        if (signal.aborted || disposed) return;
        if (refresh) {
          try { await refreshSession(); failures = 0; continue; }
          catch { useSession.getState().set({ user: null, token: null, workspace: null }); return; }
        }
        if (token !== useSession.getState().token) continue;
        if (Date.now() - opened >= 10000) failures = 0;
        failures++;
        // Fallback tối đa một lần/phút khi SSE hỏng, chỉ một tab làm; không còn polling 2 giây.
        if (failures >= 3 && Date.now() - lastFallback >= 60000) {
          lastFallback = Date.now();
          try {
            const revision = (await api.get('/sync', { signal })).data.data.revision as string;
            if (revision !== fallbackRevision) { fallbackRevision = revision; receive({ event: 'reset', cursor: '', changes: [] }, true); }
          } catch { /* Giữ cache hiện tại, chờ lần retry có backoff tiếp theo. */ }
        }
        await pause(Math.min(60000, 1000 * 2 ** Math.min(failures - 1, 6)) * (1 + Math.random() * .2), signal);
      }
    }
    function start() {
      // Tab nền nhường leader cho tab đang hiển thị; khi tất cả tab ẩn thì không giữ SSE.
      controller?.abort(); controller = null;
      if (disposed || document.visibilityState === 'hidden' || !navigator.onLine) return;
      const next = new AbortController(); controller = next;
      if (navigator.locks && channel) {
        void navigator.locks.request(name, { signal: next.signal }, () => connect(next.signal)).catch(() => {});
      } else void connect(next.signal);
    }
    function reconcile() {
      if (document.visibilityState !== 'hidden' && navigator.onLine) applyChanges(client, [resetChange]);
      start();
    }
    start();
    window.addEventListener('online', reconcile); window.addEventListener('offline', start);
    window.addEventListener('focus', reconcile); document.addEventListener('visibilitychange', reconcile);
    return () => {
      disposed = true; controller?.abort(); clearTimeout(flush); channel?.close();
      window.removeEventListener('online', reconcile); window.removeEventListener('offline', start);
      window.removeEventListener('focus', reconcile); document.removeEventListener('visibilitychange', reconcile);
    };
  }, [userId, client]);
}
