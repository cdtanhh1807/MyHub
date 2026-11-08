import { test, expect, type Browser, type Page } from '@playwright/test';
import { createServer, type ServerResponse } from 'node:http';

const folder = 'application/vnd.google-apps.folder';
const defaults = { language: 'vi', theme: 'system', view: 'list', workspace_sort: 'name', direction: 'asc' };

// Hai browser context độc lập dùng chung server giả; không truy cập dữ liệu Google/Mongo thật.
async function devices(browser: Browser) {
  let revision = 1;
  let content = 'Original content';
  const preferences = new Map<string, typeof defaults>();
  const workspaces = ['ws', 'ws2'].map((id, index) => ({ id, name: `Workspace ${index + 1}`, mimeType: folder, parents: ['root'], permissions: [] }));
  const makeFile = (id: string, name: string, parent = 'ws') => ({ id, name, mimeType: 'text/plain', parents: [parent], permissions: [] as { id: string; type: string; role: string }[], size: '16', version: '1', trashed: false });
  const files = [makeFile('text', 'shared.txt')];
  const sessions = new Map<string, { name: string; size: number; offset: number; complete: boolean }>();
  const disconnected = new Set<number>();
  const streams = new Map<ServerResponse, { index: number; device: string }>();
  const epoch = 'b'.repeat(32);
  const statistics = { checks: 0, streams: 0, fileLists: 0 };
  function broadcast(change = { kind: 'reset', workspace_ids: [] as string[], parent_ids: [] as string[], file_ids: [] as string[], tree: true, trash: true }, device?: string) {
    // Server SSE thật ghi nhiều frame trên cùng một HTTP connection, không giả lập bằng reconnect/polling.
    for (const [response, client] of streams) {
      const changes = !device || device === client.device ? [change] : [];
      response.write(`id: ${epoch}:${revision}\nevent: changes\ndata: ${JSON.stringify({ changes })}\n\n`);
    }
  }
  const server = createServer((request, response) => {
    const origin = request.headers.origin || new URL(process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173').origin;
    response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store',
      'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true' });
    const index = Number(request.headers['x-test-context']);
    streams.set(response, { index, device: String(request.headers['x-myhub-device']) });
    response.on('close', () => streams.delete(response));
    const event = request.headers['last-event-id'] === `${epoch}:${revision}` ? 'ready' : 'reset';
    response.write(`id: ${epoch}:${revision}\nevent: ${event}\ndata: {"changes":[]}\n\n`);
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address() as { port: number };
  const heartbeat = setInterval(() => { for (const response of streams.keys()) response.write(': heartbeat\n\n'); }, 5000);
  const contexts = await Promise.all([browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: 'light' }), browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: 'light' })]);
  let closed = 0;
  for (const context of contexts) context.on('close', () => {
    // Test luôn đóng server và timer riêng, không dừng backend/frontend của người dùng.
    if (++closed === contexts.length) { clearInterval(heartbeat); server.closeAllConnections(); server.close(); }
  });
  for (const [index, context] of contexts.entries()) await context.route('**/api/v1/**', async route => {
    // Các mutation thay state và revision thật của server giả, để browser kia tự phát hiện qua /sync.
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace('/api/v1', '');
    const method = request.method();
    if (path === '/sync') statistics.checks++;
    if (disconnected.has(index)) { await route.fulfill({ status: 503, json: { error: { code: 'upstream_unavailable' } } }); return; }
    const device = request.headers()['x-myhub-device'] || 'legacy';
    if (path === '/sync/events') {
      statistics.streams++;
      await route.continue({ url: `http://127.0.0.1:${address.port}/events`, headers: { ...request.headers(), 'x-test-context': String(index) } }); return;
    }
    const before = revision;
    const body = () => request.postDataJSON();
    let result: unknown = { data: {} };
    if (path === '/auth/refresh') result = { data: { access_token: 'test-only', user: { id: 'owner', name: 'Owner', provider: 'google', identity: 'owner@example.com' } } };
    else if (path === '/sync') result = { data: { revision: `test:${revision}` } };
    else if (path === '/drive-connection') result = { data: { connected: true } };
    else if (path === '/settings') {
      if (method === 'PUT') { preferences.set(device, body()); revision++; }
      result = { data: preferences.get(device) || defaults };
    } else if (path === '/workspaces') result = { files: workspaces, breadcrumbs: [] };
    else if (path === '/trash' || path.endsWith('/trash')) {
      const scope = path.split('/')[2];
      result = { files: files.filter(file => file.trashed && (!scope || file.parents.includes(scope))).map(file => ({ ...file, workspace_id: file.parents[0], workspace_name: workspaces.find(item => item.id === file.parents[0])?.name })), breadcrumbs: [] };
    } else if (/^\/workspaces\/[^/]+$/.test(path) && method === 'PATCH') {
      Object.assign(workspaces.find(item => item.id === path.split('/')[2])!, body()); revision++;
    } else if (/^\/workspaces\/[^/]+$/.test(path) && method === 'DELETE') {
      const id = path.split('/')[2];
      workspaces.splice(workspaces.findIndex(item => item.id === id), 1);
      for (const file of files) if (file.parents.includes(id)) file.trashed = true;
      revision++;
    } else if (/^\/workspaces\/[^/]+\/files$/.test(path)) {
      statistics.fileLists++;
      const parent = url.searchParams.get('parent_id') || path.split('/')[2];
      if (parent !== path.split('/')[2] && !files.some(item => item.id === parent && !item.trashed)) {
        await route.fulfill({ status: 403, json: { error: { code: 'outside_workspace' } } }); return;
      }
      result = { files: files.filter(file => !file.trashed && file.parents.includes(parent)), breadcrumbs: [] };
    } else if (path.endsWith('/folders')) {
      files.push({ ...makeFile(`folder${files.length}`, body().name, body().parent_id), mimeType: folder }); revision++;
    } else if (/\/uploads$/.test(path) && method === 'POST') {
      const id = `upload${sessions.size}`;
      const { name, size } = body(); sessions.set(id, { name, size, offset: 0, complete: false });
      result = { data: { upload_id: id, size, offset: 0, complete: false, chunk_size: 8 * 1024 * 1024 } };
    } else if (path.includes('/uploads/')) {
      const id = path.split('/').pop()!; const session = sessions.get(id)!;
      if (method === 'PUT') {
        session.offset += request.postDataBuffer()?.length || 0; session.complete = session.offset === session.size;
        if (session.complete) { files.push(makeFile(id, session.name)); revision++; }
      }
      result = { data: { upload_id: id, ...session, chunk_size: 8 * 1024 * 1024 } };
    } else if (path.includes('/files/')) {
      const [, , workspace, , id, action] = path.split('/');
      const file = files.find(item => item.id === id);
      if (!file || !file.parents.includes(workspace) || (file.trashed && action !== 'restore')) {
        await route.fulfill({ status: 403, json: { error: { code: 'outside_workspace' } } }); return;
      }
      if (!action && method === 'GET') result = file;
      else if (!action && method === 'PATCH') { Object.assign(file, body(), { version: String(Number(file.version) + 1) }); revision++; result = file; }
      else if (!action && method === 'DELETE') { file.trashed = true; revision++; }
      else if (action === 'restore') { file.trashed = false; revision++; }
      else if (action === 'preview') result = { data: { kind: 'text', preview_url: '', edit_url: '' } };
      else if (action === 'text' && method === 'GET') result = { data: { content, version: file.version, file } };
      else if (action === 'text') { content = body().content; file.version = String(Number(file.version) + 1); revision++; result = file; }
      else if (action === 'permissions' && method === 'GET') result = { data: { permissions: file.permissions, url: '' } };
      else if (action === 'permissions') { file.permissions.push({ id: 'public', type: 'anyone', role: 'reader' }); revision++; }
      else if (action === 'revisions') {
        if (method === 'POST') { content = 'Restored revision'; file.version = String(Number(file.version) + 1); revision++; }
        result = { data: { native: false, revisions: [{ id: file.version, size: '16' }] } };
      } else if (action === 'transfer') {
        const target = body();
        if (target.mode === 'copy') files.push({ ...file, id: `copy${files.length}`, name: 'copied.txt', parents: [target.target_folder_id] });
        else file.parents = [target.target_folder_id];
        revision++; result = file;
      }
    }
    if (revision !== before) {
      const parts = path.split('/');
      const isWorkspace = /^\/workspaces\/[^/]+$/.test(path);
      const change = { kind: path === '/settings' ? 'preferences' : isWorkspace ? 'workspaces' : 'files',
        workspace_ids: path === '/settings' ? [] : [parts[2], ...(path.endsWith('/transfer') ? [body().target_workspace_id] : [])],
        parent_ids: [] as string[], file_ids: parts[4] ? [parts[4]] : [], tree: isWorkspace || path.endsWith('/folders'), trash: method === 'DELETE' || path.endsWith('/restore') };
      broadcast(change, path === '/settings' ? device : undefined);
    }
    await route.fulfill({ json: result });
  });
  const pages = await Promise.all(contexts.map(context => context.newPage()));
  await Promise.all(pages.map(page => page.goto('/')));
  return { a: pages[0], b: pages[1], contexts, statistics, streams, currentName: () => files[0].name,
    externalChange: () => { files.push(makeFile('external', 'outside-app.txt')); },
    reconcileDrive: () => { revision++; broadcast(); },
    setDisconnected: (index: number, offline: boolean) => {
      if (offline) { disconnected.add(index); for (const [response, client] of streams) if (client.index === index) response.destroy(); }
      else disconnected.delete(index);
    },
    restart: () => { revision++; for (const response of streams.keys()) response.end(); } };
}

// Thiết bị thứ hai gửi request giống client thật; thiết bị thứ nhất chỉ quan sát UI, không reload.
async function mutate(page: Page, path: string, method: string, body?: unknown) {
  await page.evaluate(async ({ path, method, body }) => {
    const response = await fetch(`/api/v1${path}`, { method, headers: { Authorization: 'Bearer test-only', 'Content-Type': 'application/json', 'X-MyHub-Device': localStorage.getItem('myhub.device')! }, body: body === undefined ? undefined : JSON.stringify(body) });
    if (!response.ok) throw new Error(`Mock mutation failed: ${response.status}`);
  }, { path, method, body });
}

test('settings persist on one browser and do not change another device', async ({ browser }) => {
  // Browser khác cùng tài khoản giữ theme và ngôn ngữ riêng cả sau reload.
  const { a, b, contexts } = await devices(browser);
  try {
    await a.locator('.account-trigger').click();
    await a.getByRole('button', { name: 'Tối', exact: true }).click();
    await expect(a.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect(b.locator('html')).toHaveAttribute('data-theme', 'light');
    await a.getByLabel('Ngôn ngữ').click();
    await a.getByRole('option', { name: 'English', exact: true }).click();
    await expect(a.locator('html')).toHaveAttribute('lang', 'en');
    await expect(b.locator('html')).toHaveAttribute('lang', 'vi');
    await a.reload();
    await expect(a.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect(a.locator('html')).toHaveAttribute('lang', 'en');
    await expect.poll(async () => b.locator('html').getAttribute('data-theme')).toBe('light');
  } finally { await Promise.all(contexts.map(context => context.close())); }
});

test('mobile list and grid keep bottom navigation inside the viewport', async ({ browser }) => {
  // Bảng nhiều cột và tên dài phải cuộn nội bộ, không nới rộng viewport/thanh dưới.
  const { a, b, contexts } = await devices(browser);
  try {
    await a.setViewportSize({ width: 390, height: 844 });
    await mutate(b, '/workspaces/ws/files/text', 'PATCH', { name: 'a'.repeat(200) + '.txt' });
    await a.getByRole('button', { name: /^Workspace 1/ }).click();
    await expect(a.locator('.file-table')).toBeVisible();
    for (const view of ['list', 'grid', 'list']) {
      await a.locator('.view-toggle button').nth(view === 'list' ? 0 : 1).click();
      await expect(a.locator(view === 'list' ? '.file-table' : '.file-grid')).toBeVisible();
      const layout = await a.evaluate(() => ({ width: innerWidth, page: document.documentElement.scrollWidth,
        overflow: [...document.querySelectorAll('*')].map(element => ({ tag: element.tagName, class: element.className, right: element.getBoundingClientRect().right })).filter(item => item.right > innerWidth + 1).slice(0, 16) }));
      expect(layout.page, JSON.stringify(layout)).toBeLessThanOrEqual(layout.width);
      const navigation = await a.locator('.sidebar').boundingBox();
      expect(navigation!.width).toBeCloseTo(390, 0);
      expect(navigation!.y).toBeCloseTo(774, 0);
      await expect(a.locator('.main-navigation').getByRole('button', { name: 'Tài khoản' })).toBeInViewport();
    }
  } finally { await Promise.all(contexts.map(context => context.close())); }
});

test('other device updates lists, permissions, workspace names, trash, restore, copy and move', async ({ browser }) => {
  // Một chuỗi mutation thực thi từ browser B; browser A tự cập nhật mọi màn hình liên quan.
  const { a, b, contexts } = await devices(browser);
  try {
    await a.getByRole('button', { name: /^Workspace 1/ }).click();
    await mutate(b, '/workspaces/ws/files/text', 'PATCH', { name: 'renamed.txt' });
    await expect(a.getByRole('button', { name: 'renamed.txt', exact: true })).toBeVisible({ timeout: 10000 });
    await mutate(b, '/workspaces/ws', 'PATCH', { name: 'Renamed workspace' });
    await expect(a.getByRole('heading', { name: 'Renamed workspace', exact: true })).toBeVisible({ timeout: 10000 });
    await mutate(b, '/workspaces/ws/files/text/permissions', 'POST', { type: 'anyone', role: 'reader' });
    await expect(a.locator('.share-badge')).toHaveAttribute('title', 'Bất kỳ ai có đường liên kết', { timeout: 10000 });
    await mutate(b, '/workspaces/ws/folders', 'POST', { parent_id: 'ws', name: 'Synced folder' });
    await expect(a.getByRole('button', { name: 'Synced folder', exact: true })).toBeVisible({ timeout: 10000 });
    await mutate(b, '/workspaces/ws/files/text/transfer', 'POST', { mode: 'copy', target_workspace_id: 'ws', target_folder_id: 'ws' });
    await expect(a.getByRole('button', { name: 'copied.txt', exact: true })).toBeVisible({ timeout: 10000 });
    await mutate(b, '/workspaces/ws/files/text', 'DELETE');
    await expect(a.getByRole('button', { name: 'renamed.txt', exact: true })).toHaveCount(0, { timeout: 10000 });
    await a.locator('.main-navigation').getByRole('link', { name: 'Thùng rác' }).click();
    await expect(a.locator('.trash-row')).toContainText('renamed.txt');
    await a.locator('.trash-row').getByRole('button', { name: 'Khôi phục' }).click();
    await expect(a.locator('.trash-row')).toHaveCount(0);
    await a.locator('.main-navigation').getByRole('link', { name: 'Tệp tin' }).click();
    await expect(a.getByRole('button', { name: 'renamed.txt', exact: true })).toBeVisible();
    await mutate(b, '/workspaces/ws/files/text/transfer', 'POST', { mode: 'move', target_workspace_id: 'ws2', target_folder_id: 'ws2' });
    await expect(a.getByRole('button', { name: 'renamed.txt', exact: true })).toHaveCount(0, { timeout: 10000 });
  } finally { await Promise.all(contexts.map(context => context.close())); }
});

test('remote edits and restored revisions refresh clean editor but preserve unsaved draft', async ({ browser }) => {
  // Khi bản nháp khác dữ liệu mới, báo conflict thay vì tự ghi đè nội dung người dùng.
  const { a, b, contexts } = await devices(browser);
  try {
    await a.getByRole('button', { name: /^Workspace 1/ }).click();
    await a.getByRole('button', { name: 'shared.txt', exact: true }).click();
    await expect(a.locator('.cm-content')).toContainText('Original content');
    await mutate(b, '/workspaces/ws/files/text/text', 'PUT', { content: 'Remote saved', version: '1' });
    await expect(a.locator('.cm-content')).toContainText('Remote saved', { timeout: 10000 });
    await mutate(b, '/workspaces/ws/files/text/revisions/1/restore', 'POST', { version: '2' });
    await expect(a.locator('.cm-content')).toContainText('Restored revision', { timeout: 10000 });
    await a.locator('.cm-content').fill('Keep this draft');
    await mutate(b, '/workspaces/ws/files/text/text', 'PUT', { content: 'Remote changed again', version: '3' });
    await expect(a.locator('.conflict-box')).toBeVisible({ timeout: 10000 });
    await expect(a.locator('.cm-content')).toHaveText('Keep this draft');
    await mutate(b, '/workspaces/ws/files/text', 'DELETE');
    await expect(a.getByRole('alert').filter({ hasText: /./ })).toBeVisible({ timeout: 10000 });
    await expect(a.locator('.cm-content')).toHaveText('Keep this draft');
    await mutate(b, '/workspaces/ws', 'DELETE', { confirmation_name: 'Workspace 1' });
    await expect(a.locator('.cm-content')).toHaveText('Keep this draft');
  } finally { await Promise.all(contexts.map(context => context.close())); }
});

test('remote folder and workspace deletion recover navigation', async ({ browser }) => {
  // Không giữ người dùng ở URL folder/Workspace đã bị xóa từ máy khác.
  const { a, b, contexts } = await devices(browser);
  try {
    await mutate(b, '/workspaces/ws/folders', 'POST', { parent_id: 'ws', name: 'Folder to delete' });
    await a.getByRole('button', { name: /^Workspace 1/ }).click();
    await a.getByRole('button', { name: 'Folder to delete', exact: true }).click();
    await expect(a).toHaveURL(/folder=folder1/);
    await mutate(b, '/workspaces/ws/files/folder1', 'DELETE');
    await expect(a).not.toHaveURL(/folder=/, { timeout: 10000 });
    await expect(a.getByRole('button', { name: 'shared.txt', exact: true })).toBeVisible();
    await mutate(b, '/workspaces/ws', 'DELETE', { confirmation_name: 'Workspace 1' });
    await expect(a).toHaveURL(/\/workspaces$/, { timeout: 10000 });
    await expect(a.getByRole('button', { name: /^Workspace 1/ })).toHaveCount(0);
  } finally { await Promise.all(contexts.map(context => context.close())); }
});

test('upload completion and reconnect reconcile without reload or a new mutation', async ({ browser }) => {
  // Upload từ UI máy B phải xuất hiện trên A; focus/online và restart khôi phục dữ liệu bỏ lỡ.
  const { a, b, contexts, externalChange, restart } = await devices(browser);
  try {
    await Promise.all([a, b].map(page => page.getByRole('button', { name: /^Workspace 1/ }).click()));
    await b.locator('input[type=file]').setInputFiles({ name: 'synced-upload.txt', mimeType: 'text/plain', buffer: Buffer.from('test upload') });
    await expect(a.getByRole('button', { name: 'synced-upload.txt', exact: true })).toBeVisible({ timeout: 10000 });
    externalChange();
    await a.evaluate(() => window.dispatchEvent(new Event('online')));
    await expect(a.getByRole('button', { name: 'outside-app.txt', exact: true })).toBeVisible();
    restart();
    await mutate(b, '/workspaces/ws/files/text', 'PATCH', { name: 'after-restart.txt' });
    await expect(a.getByRole('button', { name: 'after-restart.txt', exact: true })).toBeVisible({ timeout: 10000 });
  } finally { await Promise.all(contexts.map(context => context.close())); }
});

test('SSE stays idle without polling and recovers Drive events and missed updates', async ({ browser }) => {
  // Đối soát Drive nằm ở backend, browser không phát request sau mỗi 2/30 giây nữa.
  const { a, b, contexts, statistics, setDisconnected, externalChange, reconcileDrive } = await devices(browser);
  try {
    await a.getByRole('button', { name: /^Workspace 1/ }).click();
    await expect(a.getByRole('button', { name: 'shared.txt', exact: true })).toBeVisible();
    await a.clock.install();
    await a.clock.fastForward(31000);
    expect(statistics.checks).toBe(0);
    externalChange(); reconcileDrive();
    await expect(a.getByRole('button', { name: 'outside-app.txt', exact: true })).toBeVisible({ timeout: 10000 });
    setDisconnected(0, true);
    await mutate(b, '/workspaces/ws/files/text', 'PATCH', { name: 'missed-while-offline.txt' });
    await expect(a.getByRole('button', { name: 'shared.txt', exact: true })).toBeVisible();
    setDisconnected(0, false);
    await a.evaluate(() => window.dispatchEvent(new Event('online')));
    await expect(a.getByRole('button', { name: 'missed-while-offline.txt', exact: true })).toBeVisible({ timeout: 10000 });
  } finally { await Promise.all(contexts.map(context => context.close())); }
});

test('tabs share one SSE connection and mutation bursts are batched', async ({ browser }) => {
  // Một browser/profile dùng một leader; nhiều thay đổi không gây một lần tải danh sách cho mỗi event.
  const { a, b, contexts, streams, statistics, currentName } = await devices(browser);
  try {
    const peer = await contexts[0].newPage();
    await peer.goto('/');
    await expect.poll(() => [...streams.values()].filter(client => client.index === 0).length).toBe(1);
    await a.bringToFront();
    await a.getByRole('button', { name: /^Workspace 1/ }).click();
    await expect(a.getByRole('button', { name: 'shared.txt', exact: true })).toBeVisible();
    const before = statistics.fileLists;
    await Promise.all(Array.from({ length: 20 }, (_, index) => mutate(b, '/workspaces/ws/files/text', 'PATCH', { name: `burst-${index}.txt` })));
    await expect(a.getByRole('button', { name: currentName(), exact: true })).toBeVisible();
    expect(statistics.fileLists - before).toBeLessThanOrEqual(4);
    expect(statistics.checks).toBe(0);
    await a.close();
    await peer.bringToFront();
    await expect.poll(() => [...streams.values()].filter(client => client.index === 0).length).toBe(1);
  } finally { await Promise.all(contexts.map(context => context.close())); }
});

test('SSE parser handles split UTF-8 and invalidation touches only related cache', async ({ page }) => {
  // Parser chạy trong browser thật, với từng byte/CRLF bị cắt và các query ngoài Workspace phải được giữ.
  await page.route('**/api/v1/**', route => route.fulfill({ status: 401, json: { error: { code: 'unauthorized' } } }));
  await page.goto('/');
  const result = await page.evaluate(async () => {
    const { readEventStream, affected } = await import('/src/services/sync.ts');
    const change = { kind: 'files', workspace_ids: ['ws'], parent_ids: ['sub'], file_ids: ['text'], tree: false, trash: true };
    const source = `: heartbeat\r\nid: ${'c'.repeat(32)}:7\r\nevent: changes\r\ndata: ${JSON.stringify({ changes: [change], note: 'Tiếng Việt 🙂' })}\r\n\r\n`;
    const encoded = new TextEncoder().encode(source);
    const body = new ReadableStream({ start(controller) { for (const byte of encoded) controller.enqueue(new Uint8Array([byte])); controller.close(); } });
    const received: { event: string; cursor: string }[] = [];
    await readEventStream(body, new AbortController().signal, message => received.push(message), () => {});
    return { received, matching: [['files', 'ws', 'sub'], ['files', 'ws', 'other-folder'], ['files', 'ws2', 'sub'], ['permissions', 'text'], ['metadata', 'ws', 'text'], ['settings', 'owner'], ['trash', '']].map(key => affected(key, change)) };
  });
  expect(result.received).toHaveLength(1);
  expect(result.received[0].event).toBe('changes');
  expect(result.received[0].cursor).toBe('c'.repeat(32) + ':7');
  expect(result.matching).toEqual([true, false, false, true, true, false, true]);
});
