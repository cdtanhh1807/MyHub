import { test, expect, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

// Fixture API chỉ dành cho kiểm thử UI; app runtime luôn gọi backend/Drive thật.
async function mockApi(page: Page, conflict = false, kind = 'text', multipleWorkspaces = false) {
  let preferences = { language: 'vi', theme: 'system', view: 'list', workspace_sort: 'name', direction: 'asc' };
  let workspaces = [{ id: 'ws', name: 'Dự án cá nhân', mimeType: 'application/vnd.google-apps.folder', parents: ['root'], permissions: [], createdTime: '2026-10-01T12:00:00Z' }];
  if (multipleWorkspaces) workspaces.push({ ...workspaces[0], id: 'ws2', name: 'Nghiên cứu' });
  let file = { id: 'text', name: 'README.md', mimeType: 'text/markdown', size: '12', version: '1', parents: ['ws'], permissions: [], createdTime: '2026-10-02T12:00:00Z', modifiedTime: '2026-11-01T12:00:00Z' };
  let content = '# MyHub\nHello';
  if (kind === 'pdf') file = { ...file, name: 'Guide.pdf', mimeType: 'application/pdf' };
  const uploads: { name: string; bytes: number }[] = [];
  const additional: typeof file[] = [];
  const permissions = [{ id: 'owner', type: 'user', role: 'owner', emailAddress: 'owner@example.com' }, { id: 'friend', type: 'user', role: 'commenter', emailAddress: 'friend@example.com' }];
  let conflictOnce = conflict;
  await page.route('**/api/v1/**', async route => {
    // Mock duy trì state qua mutate để phát hiện UI không refresh hoặc không gửi đúng payload.
    const request = route.request();
    const path = new URL(request.url()).pathname.replace('/api/v1', '');
    const method = request.method();
    let data: unknown;
    if (path === '/auth/refresh') data = { data: { access_token: 'ui-test-only', user: { id: 'google:cdtanhh@gmail.com', provider: 'google', identity: 'cdtanhh@gmail.com', name: 'Thanh Đạt' } } };
    else if (path === '/settings') {
      if (method === 'PUT') preferences = request.postDataJSON();
      data = { data: preferences };
    } else if (path === '/drive-connection') data = { data: { connected: true } };
    else if (path === '/workspaces') data = { files: workspaces, breadcrumbs: [] };
    else if (path === '/workspaces/ws/delete-impact') data = { data: { name: 'Dự án cá nhân', count: 2, confirmation_token: 'ui-test-snapshot' } };
    else if (path === '/workspaces/ws' && method === 'DELETE') { workspaces = []; data = { data: { trashed: true } }; }
    else if (/^\/workspaces\/[^/]+\/files$/.test(path)) {
      const workspaceId = path.split('/')[2];
      data = { files: workspaceId === 'ws' ? [file, ...additional] : [{ ...file, id: 'text2', name: 'Roadmap.md', parents: [workspaceId] }], breadcrumbs: workspaces.filter(item => item.id === workspaceId) };
    }
    else if (path === '/workspaces/ws/upload') {
      const name = new URL(request.url()).searchParams.get('name')!;
      const bytes = request.postDataBuffer()?.length || 0;
      uploads.push({ name, bytes });
      const uploaded = { ...file, id: 'uploaded' + uploads.length, name, size: String(bytes) };
      additional.push(uploaded); data = uploaded;
    }
    else if (path.endsWith('/preview')) data = { data: { kind, preview_url: 'https://drive.google.com/file/d/text/preview', edit_url: 'https://drive.google.com/file/d/text/view' } };
    else if (path.endsWith('/content') && kind === 'pdf') { await route.fulfill({ contentType: 'application/pdf', body: pdfFixture() }); return; }
    else if (path.endsWith('/access')) data = { data: { ready: true } };
    else if (path.endsWith('/permissions') && method === 'GET') data = { data: { permissions, url: 'https://drive.google.com/file/d/text/view' } };
    else if (path.endsWith('/permissions/friend') && method === 'PATCH') { permissions[1].role = request.postDataJSON().role; data = { data: permissions[1] }; }
    else if (path === '/archive-formats') data = { data: { zip: true, rar: false, '7z': false, tar: true, gz: true, tgz: true, jar: true, iso: true } };
    else if (path.endsWith('/text') && method === 'GET') data = { data: { content, version: file.version, file } };
    else if (path.endsWith('/text') && method === 'PUT') {
      const body = request.postDataJSON();
      if (conflictOnce && body.strategy === 'normal') { conflictOnce = false; await route.fulfill({ status: 409, json: { error: { code: 'conflict' } } }); return; }
      content = body.content;
      file = { ...file, version: '2' };
      data = body.strategy === 'copy' ? { ...file, id: 'copy', name: 'README (copy).md' } : file;
    } else data = { data: {} };
    await route.fulfill({ json: data });
  });
  return { uploads };
}

// PDF ASCII tự tạo có xref hợp lệ để kiểm tra pdf.js/worker bằng trình duyệt thật.
function pdfFixture() {
  const stream = 'BT /F1 18 Tf 20 350 Td (MyHub PDF test) Tj ET';
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`];
  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  for (const [index, object] of objects.entries()) { offsets.push(pdf.length); pdf += `${index + 1} 0 obj\n${object}\nendobj\n`; }
  const xref = pdf.length;
  pdf += `xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(pdf);
}

test('desktop workspace → editor → save, real browser screenshot', async ({ page }) => {
  // Kiểm tra luồng chính và trạng thái dirty/save bằng tương tác trình duyệt thật.
  await page.setViewportSize({ width: 1440, height: 960 });
  await mockApi(page);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Chào mừng trở lại, Liam Cao' })).toBeVisible();
  const label = page.locator('.main-navigation .nav-item').first().locator('span');
  expect(await label.evaluate(element => element.scrollWidth <= element.clientWidth)).toBeTruthy();
  await mkdir('../data/previews', { recursive: true });
  await page.screenshot({ path: '../data/previews/myhub-workspaces.png', fullPage: true });
  await page.getByRole('button', { name: /^Dự án cá nhân/ }).click();
  await expect(page.getByRole('heading', { name: 'Dự án cá nhân' })).toBeVisible();
  await page.screenshot({ path: '../data/previews/myhub-files.png', fullPage: true });
  await page.getByRole('button', { name: 'README.md', exact: true }).click();
  await expect(page.locator('.cm-content')).toBeVisible();
  await page.locator('.cm-content').fill('# Updated in MyHub');
  await expect(page.getByText('Có thay đổi chưa lưu')).toBeVisible();
  await page.getByRole('button', { name: 'Lưu', exact: true }).click();
  await expect(page.getByText('Đã lưu thay đổi')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Lưu', exact: true })).toBeDisabled();
  expect(errors).toEqual([]);
});

test('stale editor preserves text and offers save-copy', async ({ page }) => {
  // Khi backend báo 409, nội dung đang nhập phải còn và nút ghi đè không tự chạy.
  await mockApi(page, true);
  await page.goto('/');
  await page.getByRole('button', { name: /^Dự án cá nhân/ }).click();
  await page.getByRole('button', { name: 'README.md', exact: true }).click();
  await page.locator('.cm-content').fill('Keep my work');
  await page.getByRole('button', { name: 'Lưu', exact: true }).click();
  await expect(page.getByText('Tệp đã thay đổi trên thiết bị khác')).toBeVisible();
  await expect(page.locator('.cm-content')).toContainText('Keep my work');
  await page.getByRole('button', { name: 'Lưu thành bản sao' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('workspace deletion requires both steps and exact name', async ({ page }) => {
  // Không được gửi DELETE từ bước cảnh báo hoặc khi nhập sai tên.
  await mockApi(page);
  await page.goto('/');
  await page.getByLabel('Thao tác').click();
  await page.getByRole('button', { name: 'Chuyển vào thùng rác', exact: true }).click();
  await expect(page.getByText(/2 tệp\/thư mục/)).toBeVisible();
  await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
  const confirmButton = page.getByRole('button', { name: 'Xác nhận', exact: true });
  await expect(confirmButton).toBeDisabled();
  await page.getByPlaceholder('Dự án cá nhân').fill('wrong');
  await expect(confirmButton).toBeDisabled();
  await page.getByPlaceholder('Dự án cá nhân').fill('Dự án cá nhân');
  await confirmButton.click();
  await expect(page.getByText('Bắt đầu với một không gian mới')).toBeVisible();
});

test('portrait navigation, account sheet, language and dark mode', async ({ page }) => {
  // Kiểm tra orientation thật, không chỉ thu nhỏ chiều rộng desktop.
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Chào mừng trở lại, Liam Cao' })).toBeVisible();
  const navigation = await page.locator('.sidebar').boundingBox();
  expect(navigation!.y).toBeGreaterThan(700);
  await page.locator('.main-navigation').getByRole('button', { name: 'Tài khoản' }).click();
  await page.getByRole('button', { name: 'Tối', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(16, 23, 34)');
  await page.getByLabel('Ngôn ngữ').click();
  await page.getByRole('option', { name: 'English', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Account', exact: true })).toBeVisible();
  const sheet = await page.getByRole('dialog').boundingBox();
  expect(sheet!.y + sheet!.height).toBeCloseTo(844, -1);
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await mkdir('../data/previews', { recursive: true });
  await page.screenshot({ path: '../data/previews/myhub-mobile-dark.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.setViewportSize({ width: 844, height: 390 });
  await expect(page.locator('.sidebar')).toHaveCSS('width', '185px');
  const sidebar = await page.locator('.sidebar').boundingBox();
  expect(sidebar!.x).toBe(0); expect(sidebar!.width).toBeLessThan(220);
});

test('upload queue sends raw files and refreshes the folder', async ({ page }) => {
  // Hai file thật trong browser đi qua raw upload với đúng tên và số byte.
  const { uploads } = await mockApi(page);
  await page.goto('/');
  await page.getByRole('button', { name: /^Dự án cá nhân/ }).click();
  await page.locator('input[type=file]').setInputFiles([{ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('hello') }, { name: 'config.json', mimeType: 'application/json', buffer: Buffer.from('{}') }]);
  await expect(page.getByText('Đã tải lên', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'notes.txt', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'config.json', exact: true })).toBeVisible();
  expect(uploads).toEqual([{ name: 'notes.txt', bytes: 5 }, { name: 'config.json', bytes: 2 }]);
});

test('PDF viewer renders locally and zooms', async ({ page }) => {
  // Phát hiện lỗi worker/asset PDF mà TypeScript build không thể kiểm chứng.
  await mockApi(page, false, 'pdf');
  await page.goto('/');
  await page.getByRole('button', { name: /^Dự án cá nhân/ }).click();
  await page.getByRole('button', { name: 'Guide.pdf', exact: true }).click();
  await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();
  await expect(page.locator('.react-pdf__Page__textContent')).toContainText('MyHub PDF test');
  await page.getByRole('button', { name: 'Phóng to', exact: true }).click();
  await expect(page.getByText('125%', { exact: true })).toBeVisible();
});

test('panel dropdown switches directly between workspaces, including when collapsed', async ({ page }) => {
  // Click trigger chỉ mở menu; chọn ID mới đi thẳng vào Files, không vòng qua trang Workspace.
  await page.setViewportSize({ width: 1440, height: 960 });
  await mockApi(page, false, 'text', true);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Chào mừng trở lại, Liam Cao' })).toBeVisible();
  const switcher = page.getByRole('combobox', { name: 'Chọn không gian', exact: true });
  await switcher.click();
  await expect(page.getByRole('listbox')).toHaveCSS('border-radius', '9px');
  await expect(page.getByRole('option')).toHaveCount(2);
  await page.getByRole('option', { name: 'Dự án cá nhân', exact: true }).click();
  await expect(page).toHaveURL(/\/files\?workspace=ws$/);
  await expect(page.getByRole('heading', { name: 'Dự án cá nhân' })).toBeVisible();
  await switcher.click();
  await expect(page).toHaveURL(/\/files\?workspace=ws$/);
  await page.screenshot({ path: '../data/previews/myhub-workspace-switcher.png', fullPage: true });
  await page.getByRole('option', { name: 'Nghiên cứu', exact: true }).click();
  await expect(page).toHaveURL(/\/files\?workspace=ws2$/);
  await expect(page.getByRole('heading', { name: 'Nghiên cứu' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Roadmap.md', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Thu gọn thanh bên' }).click();
  await switcher.click();
  await page.getByRole('option', { name: 'Dự án cá nhân', exact: true }).click();
  await expect(page).toHaveURL(/\/files\?workspace=ws$/);
});

test('dropdowns match their rounded controls and support keyboard inside account dialog', async ({ page }) => {
  // Menu trong dialog phải nằm trên top layer, Escape chỉ đóng menu và giữ dialog mở.
  await mockApi(page);
  await page.goto('/');
  await page.locator('.account-trigger').click();
  const language = page.getByLabel('Ngôn ngữ');
  await language.focus();
  await language.press('ArrowDown');
  const popup = page.getByRole('listbox');
  await expect(popup).toBeVisible();
  await expect(popup).toHaveCSS('border-radius', '8px');
  await language.press('Escape');
  await expect(popup).toHaveCount(0);
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(language).toBeFocused();
  await language.press('ArrowDown');
  await language.press('End');
  await language.press('Enter');
  await expect(page.getByRole('heading', { name: 'Account', exact: true })).toBeVisible();
  await page.getByLabel('Language').click();
  await page.screenshot({ path: '../data/previews/myhub-account-dropdown.png', fullPage: true });
  await page.getByRole('option', { name: 'Tiếng Việt', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Tài khoản', exact: true })).toBeVisible();
});

test('share role dropdown handles Fragment options and persists the selected role', async ({ page }) => {
  // Share tái dùng Fragment option, phải giữ đủ role khi chuyển sang component mới.
  await mockApi(page);
  await page.goto('/');
  await page.getByRole('button', { name: /^Dự án cá nhân/ }).click();
  await page.getByLabel('Thao tác').click();
  await page.getByRole('button', { name: 'Chia sẻ', exact: true }).click();
  const role = page.getByRole('combobox', { name: 'Loại friend@example.com', exact: true });
  await role.click();
  await expect(page.getByRole('option')).toHaveCount(3);
  await page.getByRole('option', { name: 'Người chỉnh sửa', exact: true }).click();
  await expect(role).toHaveText('Người chỉnh sửa');
  await expect(page.getByText('Đã lưu thay đổi', { exact: true })).toBeVisible();
});

test('archive dropdown preserves disabled formats and skips them with keyboard', async ({ page }) => {
  // Không được chọn định dạng thiếu công cụ, kể cả khi thao tác bằng bàn phím.
  await mockApi(page);
  await page.goto('/');
  await page.getByRole('button', { name: /^Dự án cá nhân/ }).click();
  await page.getByLabel('Trang chính').click();
  // Dùng thư mục root qua fixture bổ sung chỉ cho test này, không tạo dữ liệu Drive thật.
  await page.route('**/api/v1/workspaces/ws/files?*', route => route.fulfill({ json: { files: [{ id: 'sub', name: 'Folder', mimeType: 'application/vnd.google-apps.folder', parents: ['ws'], permissions: [] }], breadcrumbs: [{ id: 'ws', name: 'Dự án cá nhân', mimeType: 'application/vnd.google-apps.folder', parents: ['root'], permissions: [] }] } }));
  await page.getByRole('button', { name: 'Làm mới', exact: true }).click();
  await page.getByLabel('Thao tác').click();
  await page.getByRole('button', { name: 'Tải thư mục', exact: true }).click();
  const format = page.getByLabel('Định dạng tải xuống');
  await format.click();
  await expect(page.getByRole('option', { name: /RAR/ })).toBeDisabled();
  await expect(page.getByRole('option', { name: /7Z/ })).toBeDisabled();
  await format.press('ArrowDown');
  await format.press('Enter');
  await expect(format).toHaveText('TAR');
});
