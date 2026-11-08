import { Select } from '../components/Select';
import { lazy, Suspense, useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Boxes, Files as FilesIcon, Trash2, UserRound, PanelLeftClose, PanelLeftOpen, LogOut, ChevronDown, ArrowUpRight, ShieldCheck, Cloud, CodeXml as Github, Sun, Moon, Monitor } from 'lucide-react';
import { api, API_URL, downloadFile, errorCode, refreshSession } from '../services/api';
import { useSession } from '../store/session';
import { usePreferences } from '../hooks/usePreferences';
import { Empty, FeedbackProvider, Loading, Modal, useFeedback } from '../components/ui';
import { Workspaces } from '../pages/Workspaces';
import { Files } from '../pages/Files';
import { Trash } from '../pages/Trash';
import { NameDialog, DeleteDialog, TransferDialog, ShareDialog, ArchiveDialog, HistoryDialog, DetailsDialog } from '../features/files/Dialogs';
import type { DriveFile, FileList, Preferences } from '../types';

import { WorkspaceSwitcher } from '../features/workspaces/WorkspaceSwitcher';
import { useLiveSync } from '../hooks/useLiveSync';

const Viewer = lazy(() => import('../features/preview/Viewer'));

// Dùng ảnh logo trong public; chế độ thu gọn vẫn có tên thương hiệu truy cập được.
function Brand({ compact = false }: { compact?: boolean }) { return <div className="brand"><span className="brand-icon"><img src="/myhub_logo.png" alt={compact ? 'MyHub' : ''} width={35} height={35} /></span>{!compact && <span>My<span className="brand-hub">Hub</span><sup>01</sup></span>}</div>; }

// Login công khai chỉ có hai provider; việc whitelist luôn được thực thi ở backend.
function Login({ error }: { error: string }) {
  const { t, i18n } = useTranslation();
  return <div className="login-layout"><section className="login-story"><Brand /><div className="story-copy"><span className="eyebrow">YOUR PERSONAL DIGITAL SPACE</span><h1>{t('loginTitle')}</h1><p>{t('loginSubtitle')}</p><div className="folder-art" aria-hidden="true"><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-folder folder-back" /><div className="art-folder folder-front"><img className="folder-brand-logo" src="/myhub_logo.png" alt="" width={48} height={48} /><span>Everything, connected.</span><i /></div><span className="art-chip chip-code">&lt;/&gt;</span><span className="art-chip chip-doc">Aa</span><span className="art-chip chip-drive"><Cloud size={23} /></span></div></div><footer><ShieldCheck size={16} />{t('secureNote')}</footer></section><section className="login-panel"><button className="language-switch" onClick={() => { const language = i18n.language === 'vi' ? 'en' : 'vi'; localStorage.setItem('myhub.language', language); useSession.getState().set({ preferences: { ...useSession.getState().preferences, language } }); void i18n.changeLanguage(language); }}>{i18n.language === 'vi' ? 'English' : 'Tiếng Việt'}</button><div className="login-form"><span className="login-welcome-icon"><img src="/myhub_logo.png" alt="MyHub" width={55} height={55} /></span><h2>{t('loginHeading')}</h2><p>{t('loginHint')}</p>{error && <div role="alert" className="error-banner">{t(error, { defaultValue: t('error') })}</div>}<a className="oauth-button" href={`${API_URL}/auth/google/login`}><span className="google-g">G</span>{t('google')}<ArrowUpRight size={17} /></a><a className="oauth-button" href={`${API_URL}/auth/github/login`}><Github size={22} />{t('github')}<ArrowUpRight size={17} /></a><div className="login-restricted"><ShieldCheck size={15} />{t('loginRestricted')}</div></div><footer>MyHub <span>·</span> {t('tagline')}</footer></section></div>;
}

// Account dùng chung trong sidebar và bottom-sheet trên màn hình dọc.
function Account({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const { user, set } = useSession();
  const { preferences, update } = usePreferences();
  const { run } = useFeedback();
  const client = useQueryClient();
  return <Modal title={t('account')} onClose={onClose}><div className="modal-body account-body"><div className="account-profile"><Avatar /><h3>{user!.name}</h3><span className="muted">{user!.identity}</span><span className="pill">{user!.provider === 'google' ? 'Google' : 'GitHub'}</span></div><label className="field-label">{t('language')}<Select value={preferences.language} onChange={event => void run(() => update({ language: event.target.value as Preferences['language'] }))}><option value="vi">Tiếng Việt</option><option value="en">English</option></Select></label><label className="field-label">{t('theme')}</label><div className="theme-picker">{(['light', 'dark', 'system'] as const).map((theme, i) => { const Icon = [Sun, Moon, Monitor][i]; return <button key={theme} className={preferences.theme === theme ? 'active' : ''} onClick={() => void run(() => update({ theme }))}><Icon size={21} />{t(theme)}</button>; })}</div><p className="muted small">{t('disconnectHint')}</p><button className="secondary full-width" onClick={() => void run(async () => { const response = await api.post('/drive-connection/authorize'); location.assign(response.data.data.url); })}><Cloud size={17} />{t('connect')}</button></div><footer className="modal-footer"><button className="danger full-width" onClick={() => void run(async () => { await api.post('/auth/logout'); set({ user: null, token: null, workspace: null }); client.clear(); onClose(); })}><LogOut size={17} />{t('logout')}</button></footer></Modal>;
}

// Avatar có fallback chữ cái, không làm mất bố cục khi profile không có ảnh.
function Avatar() {
  const user = useSession(s => s.user)!;
  const [failed, setFailed] = useState(false);
  return <span className="avatar">{user.avatar && !failed ? <img src={user.avatar} alt="" onError={() => setFailed(true)} referrerPolicy="no-referrer" /> : user.name[0].toUpperCase()}</span>;
}

// Shell là danh sách navigation mở rộng được; orientation quyết định sidebar hoặc bottom navigation.
function Shell() {
  const { t } = useTranslation();
  const { user, workspace, collapsed, set } = useSession();
  usePreferences();
  useLiveSync();
  const [accountOpen, setAccountOpen] = useState(false);
  const [action, setAction] = useState<{ type: string; file?: DriveFile } | null>(null);
  const { run } = useFeedback();
  const client = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const connection = useQuery({ queryKey: ['connection'], queryFn: async () => (await api.get('/drive-connection')).data.data as { connected: boolean; reason?: string } });
  const workspaces = useQuery({ queryKey: ['workspaces'], enabled: !!connection.data?.connected, queryFn: async () => (await api.get('/workspaces')).data as FileList });
  // C?c dialog ?ang m? c?ng nh?n metadata m?i; l?i ph?m vi kh?ng t? ??ng form ?ang nh?p.
  const actionMetadata = useQuery({ queryKey: ['metadata', workspace?.id, action?.file?.id],
    enabled: !!workspace && !!action?.file?.id && !['workspaceCreate', 'workspaceRename', 'workspaceDelete', 'folderCreate', 'open'].includes(action.type),
    queryFn: async () => (await api.get(`/workspaces/${workspace!.id}/files/${action!.file!.id}`)).data as DriveFile });
  const actionFile = actionMetadata.data || action?.file;

  useEffect(() => {
    // URL lưu ID Workspace; dữ liệu luôn lấy lại từ Drive để đổi tên bên ngoài cũng hiện đúng.
    const requested = params.get('workspace');
    if (!workspaces.data) return;
    const found = workspaces.data.files.find(item => item.id === (requested || workspace?.id));
    if (found && (workspace?.id !== found.id || workspace?.name !== found.name)) set({ workspace: found });
    // Workspace bị xóa từ máy khác: bỏ lựa chọn cũ; giữ viewer đang mở để không mất bản nháp.
    if (!found && workspace && !action) { set({ workspace: null }); if (location.pathname === '/files') navigate('/workspaces', { replace: true }); }
  }, [workspaces.data, params, workspace?.id, workspace?.name, set, action, location.pathname, navigate]);
  function choose(file: DriveFile) { set({ workspace: file }); navigate(`/files?workspace=${file.id}`); }
  function closeAction() { setAction(null); }
  function done() {
    // Sau mutate, vô hiệu hóa cache đọc; xóa Workspace đang chọn thì về trang chọn.
    if (action?.type === 'workspaceDelete' && action.file?.id === workspace?.id) { set({ workspace: null }); navigate('/workspaces'); }
    setAction(null); void client.invalidateQueries();
  }
  function onAction(type: string, file?: DriveFile) {
    if (type === 'download') { void run(() => downloadFile(workspace!.id, file!.id)); return; }
    setAction({ type, file });
  }
  const navigation = [{ path: '/workspaces', key: 'workspaces', icon: Boxes }, { path: `/files${workspace ? `?workspace=${workspace.id}` : ''}`, key: 'files', icon: FilesIcon }, { path: '/trash', key: 'trash', icon: Trash2 }];
  const folderId = params.get('folder') || workspace?.id;
  const siblings = client.getQueriesData<FileList>({ queryKey: ['files', workspace?.id, folderId] }).find(([, value]) => !!value)?.[1]?.files || (action?.file ? [action.file] : []);
  return <div className={`app-shell ${collapsed ? 'collapsed' : ''}`}><aside className="sidebar"><div className="sidebar-top"><Brand compact={collapsed} /><button className="icon-button collapse-button" aria-label={t('collapse')} onClick={() => set({ collapsed: !collapsed })}>{collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}</button></div><WorkspaceSwitcher workspaces={workspaces.data?.files || []} selected={workspace} onSelect={choose} /><span className="navigation-label">MY HUB</span><nav className="main-navigation">{navigation.map(({ path, key, icon: Icon }) => <NavLink key={key} className={({ isActive }) => `nav-item ${isActive && !(key === 'files' && !workspace) ? 'active' : ''} ${key === 'files' && !workspace ? 'disabled' : ''}`} to={key === 'files' && !workspace ? '/workspaces' : path}><Icon size={20} /><span>{t(key)}</span>{key === 'workspaces' && <small>{workspaces.data?.files.length ?? '—'}</small>}</NavLink>)}<button className="nav-item mobile-account" onClick={() => setAccountOpen(true)}><UserRound size={20} /><span>{t('account')}</span></button></nav><div className="sidebar-bottom"><div className="drive-status"><Cloud size={18} /><span>{t(connection.data?.connected ? 'connected' : 'connect')}</span><span className={`dot ${!connection.data?.connected ? 'offline' : ''}`} /></div><button className="account-trigger" onClick={() => setAccountOpen(true)}><Avatar /><span><strong>{user!.name}</strong><small>{user!.identity}</small></span><ChevronDown size={15} /></button><button className="sidebar-logout" onClick={() => void run(async () => { await api.post('/auth/logout'); set({ user: null, token: null, workspace: null }); client.clear(); })}><LogOut size={15} /><span>{t('logout')}</span></button></div></aside>
    <div className="main-column"><header className="topbar"><div><span className="muted">MyHub</span><ChevronDown size={12} className="topbar-chevron" /><strong>{t(location.pathname.startsWith('/files') ? 'files' : location.pathname.startsWith('/trash') ? 'trash' : 'workspaces')}</strong></div><span className="private-label"><ShieldCheck size={14} />{t('private')}</span><button className="mobile-profile" aria-label={t('account')} onClick={() => setAccountOpen(true)}><Avatar /></button></header><main className="main-content">{connection.isPending ? <Loading /> : connection.isError ? <Empty title={t(errorCode(connection.error), { defaultValue: t('error') })} action={<button className="secondary" onClick={() => void connection.refetch()}>{t('retry')}</button>} /> : !connection.data.connected ? <div className="connect-card"><span className="connect-icon"><Cloud size={42} strokeWidth={1.3} /></span><span className="eyebrow">GOOGLE DRIVE × MYHUB</span><h1>{t('connectTitle')}</h1><p>{t('connectDescription')}</p>{connection.data.reason && connection.data.reason !== 'drive_not_connected' && <p className="error-text">{t(connection.data.reason, { defaultValue: t('error') })}</p>}<button className="primary" onClick={() => void run(async () => { const response = await api.post('/drive-connection/authorize'); window.location.assign(response.data.data.url); })}>{t('connect')}<ArrowUpRight size={18} /></button></div> : workspaces.isPending ? <Loading /> : workspaces.isError ? <Empty title={t(errorCode(workspaces.error), { defaultValue: t('error') })} action={<button className="secondary" onClick={() => void workspaces.refetch()}>{t('retry')}</button>} /> : <Routes><Route path="/workspaces" element={<Workspaces files={workspaces.data.files} onSelect={choose} onAction={onAction} />} /><Route path="/files" element={workspace ? <Files key={workspace.id} onAction={onAction} /> : <Navigate to="/workspaces" replace />} /><Route path="/trash" element={<Trash />} /><Route path="*" element={<Navigate to="/workspaces" replace />} /></Routes>}</main><footer className="app-footer"><span>MyHub <span className="muted">/</span> v0.1</span><span>{t('tagline')}</span></footer></div>
    {accountOpen && <Account onClose={() => setAccountOpen(false)} />}
    {action && (['workspaceCreate', 'workspaceRename', 'folderCreate', 'rename'].includes(action.type) ? <NameDialog {...action} file={actionFile} action={action.type} onClose={closeAction} onDone={done} /> : ['workspaceDelete', 'delete'].includes(action.type) ? <DeleteDialog file={actionFile} workspaceDelete={action.type === 'workspaceDelete'} onClose={closeAction} onDone={done} /> : action.type === 'share' ? <ShareDialog file={actionFile} onClose={closeAction} onDone={done} /> : action.type === 'move' || action.type === 'copy' ? <TransferDialog file={actionFile} mode={action.type} onClose={closeAction} onDone={done} /> : action.type === 'archive' ? <ArchiveDialog file={actionFile} onClose={closeAction} onDone={done} /> : action.type === 'history' ? <HistoryDialog file={actionFile} onClose={closeAction} onDone={done} /> : action.type === 'details' ? <DetailsDialog file={actionFile} onClose={closeAction} onDone={done} /> : action.type === 'open' ? <Suspense fallback={<Modal title={t('loading')} onClose={closeAction}><Loading /></Modal>}><Viewer file={action.file!} siblings={siblings} onClose={closeAction} onSelect={file => setAction({ type: 'open', file })} onChanged={() => { void client.invalidateQueries({ queryKey: ['files'] }); }} /></Suspense> : null)}
  </div>;
}

// Bootstrap đọc refresh cookie để phục hồi phiên, không lấy token từ URL/localStorage.
export default function App() {
  const { ready, user, set } = useSession();
  const [error, setError] = useState(new URLSearchParams(window.location.search).get('error') || '');
  useEffect(() => {
    void refreshSession().catch(failure => { if (errorCode(failure) !== 'unauthorized') setError(errorCode(failure)); }).finally(() => set({ ready: true }));
  }, [set]);
  return <FeedbackProvider>{!ready ? <div className="boot"><Brand /><Loading /></div> : user ? <Shell /> : <Login error={error} />}</FeedbackProvider>;
}
