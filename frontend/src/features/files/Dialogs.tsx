import { Select } from '../../components/Select';
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ChevronRight, Folder, ArrowUp, Copy, Globe, LockKeyhole, ShieldAlert, Download, History } from 'lucide-react';
import { api, downloadFile, errorCode } from '../../services/api';
import { Modal, Loading, Empty, useFeedback, FileIcon } from '../../components/ui';
import { FOLDER, type DriveFile, type FileList, type Permission } from '../../types';
import { useSession } from '../../store/session';
import { fileDate, fileSize } from '../../utils/format';

export interface DialogProps { file?: DriveFile; onClose: () => void; onDone: () => void }

// Form tên dùng chung cho Workspace/folder/file, chỉ đóng sau khi API thành công.
export function NameDialog({ file, action, onClose, onDone }: DialogProps & { action: string }) {
  const { t } = useTranslation();
  const workspace = useSession(s => s.workspace);
  const { run } = useFeedback();
  const [name, setName] = useState(action.includes('Create') ? '' : file?.name || '');
  const [busy, setBusy] = useState(false);
  const title = action === 'workspaceCreate' ? 'newWorkspace' : action === 'folderCreate' ? 'newFolder' : 'rename';
  async function submit() {
    // Controller nhận đúng endpoint theo loại thao tác; pending luôn được giải phóng.
    setBusy(true);
    try {
      if (action === 'workspaceCreate') await api.post('/workspaces', { name });
      else if (action === 'workspaceRename') await api.patch(`/workspaces/${file!.id}`, { name });
      else if (action === 'folderCreate') await api.post(`/workspaces/${workspace!.id}/folders`, { name, parent_id: file!.id });
      else await api.patch(`/workspaces/${workspace!.id}/files/${file!.id}`, { name });
      onDone();
    } finally { setBusy(false); }
  }
  return <Modal title={t(title)} onClose={onClose}><form onSubmit={event => { event.preventDefault(); void run(submit); }}><div className="modal-body"><label className="field-label">{t(action.startsWith('workspace') ? 'workspaceName' : action === 'folderCreate' ? 'folderName' : 'fileName')}<input autoFocus required maxLength={240} value={name} onChange={event => setName(event.target.value)} /></label></div><footer className="modal-footer"><button type="button" className="secondary" disabled={busy} onClick={onClose}>{t('cancel')}</button><button className="primary" disabled={busy || !name.trim()}>{t(busy ? 'loading' : action.includes('Create') ? 'create' : 'save')}</button></footer></form></Modal>;
}

// Xóa Workspace bắt buộc xem ảnh hưởng rồi nhập lại tên; file thường chỉ cần xác nhận.
export function DeleteDialog({ file, workspaceDelete, onClose, onDone }: DialogProps & { workspaceDelete: boolean }) {
  const { t } = useTranslation();
  const workspace = useSession(s => s.workspace);
  const { run } = useFeedback();
  const [step, setStep] = useState(1);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const impact = useQuery({ queryKey: ['impact', file!.id], enabled: workspaceDelete, queryFn: async () => (await api.get(`/workspaces/${file!.id}/delete-impact`)).data.data as { name: string; count: number; confirmation_token: string } });
  async function submit() {
    // Snapshot token gắn tên/số mục được gửi cùng xác nhận; thay đổi cây sẽ bị backend chặn.
    setBusy(true);
    try {
      if (workspaceDelete) await api.delete(`/workspaces/${file!.id}`, { data: { confirmation_name: name, confirmation_token: impact.data!.confirmation_token } });
      else await api.delete(`/workspaces/${workspace!.id}/files/${file!.id}`);
      onDone();
    } finally { setBusy(false); }
  }
  return <Modal title={t(workspaceDelete ? 'deleteWorkspaceTitle' : 'delete')} onClose={onClose}><div className="modal-body"><div className="warning-icon"><ShieldAlert size={27} /></div>{workspaceDelete ? impact.isPending ? <Loading /> : impact.isError ? <p className="error-text">{t(errorCode(impact.error), { defaultValue: t('error') })}</p> : <><p>{t('deleteImpact', { name: impact.data.name, count: impact.data.count })}</p>{step === 2 && <label className="field-label">{t('deleteWorkspaceStep')}<input autoFocus value={name} onChange={event => setName(event.target.value)} placeholder={impact.data.name} /></label>}</> : <><strong>{file!.name}</strong><p>{t('deleteFileHint')}</p></>}</div><footer className="modal-footer"><button className="secondary" disabled={busy} onClick={onClose}>{t('cancel')}</button>{workspaceDelete && step === 1 ? <button className="danger" disabled={!impact.data} onClick={() => setStep(2)}>{t('continue')}</button> : <button className="danger" disabled={busy || (workspaceDelete && name !== impact.data?.name)} onClick={() => void run(submit)}>{t(busy ? 'loading' : 'confirm')}</button>}</footer></Modal>;
}

// Folder picker duyệt được cả Workspace khác, backend kiểm tra nguồn/đích độc lập.
export function TransferDialog({ file, mode, onClose, onDone }: DialogProps & { mode: 'move' | 'copy' }) {
  const { t } = useTranslation();
  const source = useSession(s => s.workspace)!;
  const [workspace, setWorkspace] = useState(source.id);
  const [folder, setFolder] = useState(source.id);
  const [busy, setBusy] = useState(false);
  const { run } = useFeedback();
  const workspaces = useQuery({ queryKey: ['workspaces'], queryFn: async () => (await api.get('/workspaces')).data as FileList });
  const folders = useQuery({ queryKey: ['destination', workspace, folder], queryFn: async () => (await api.get(`/workspaces/${workspace}/files`, { params: { parent_id: folder } })).data as FileList });
  async function submit() {
    // Không tự suy diễn folder đích từ tên; mọi tham chiếu đều dùng Drive ID.
    setBusy(true);
    try { await api.post(`/workspaces/${source.id}/files/${file!.id}/transfer`, { target_workspace_id: workspace, target_folder_id: folder, mode }); onDone(); }
    finally { setBusy(false); }
  }
  return <Modal title={`${t(mode)} · ${file!.name}`} onClose={onClose}><div className="modal-body"><label className="field-label">{t('workspace')}<Select value={workspace} onChange={event => { setWorkspace(event.target.value); setFolder(event.target.value); }}>{workspaces.data?.files.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></label>
    <nav className="breadcrumbs">{folders.data?.breadcrumbs.map(item => <span key={item.id}><ChevronRight size={13} /><button onClick={() => setFolder(item.id)}>{item.name}</button></span>)}</nav><div className="folder-picker">{folders.isPending ? <Loading /> : folders.isError ? <p className="error-text">{t(errorCode(folders.error), { defaultValue: t('error') })}</p> : <>{folder !== workspace && <button className="picker-folder" onClick={() => setFolder(folders.data.breadcrumbs.at(-2)?.id || workspace)}><ArrowUp size={19} />{t('up')}</button>}{folders.data.files.filter(item => item.mimeType === FOLDER && item.id !== file!.id).map(item => <button key={item.id} className="picker-folder" onClick={() => setFolder(item.id)}><Folder size={20} /><span>{item.name}</span><ChevronRight size={16} /></button>)}</>}</div></div><footer className="modal-footer"><button className="secondary" onClick={onClose} disabled={busy}>{t('cancel')}</button><button className="primary" disabled={busy || !folders.data} onClick={() => void run(submit)}>{t(busy ? 'loading' : 'selectFolder')}</button></footer></Modal>;
}

// Share dialog thao tác trực tiếp permissions Drive, không tạo link MyHub công khai.
export function ShareDialog({ file, onClose, onDone }: DialogProps) {
  const { t } = useTranslation();
  const workspace = useSession(s => s.workspace)!;
  const base = `/workspaces/${workspace.id}/files/${file!.id}/permissions`;
  const query = useQuery({ queryKey: ['permissions', file!.id], queryFn: async () => (await api.get(base)).data.data as { permissions: Permission[]; url: string } });
  const { run, notify } = useFeedback();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('reader');
  const [notifyEmail, setNotifyEmail] = useState(false);
  const [access, setAccess] = useState('restricted');
  const [linkRole, setLinkRole] = useState('reader');
  const [busy, setBusy] = useState(false);
  const anyone = query.data?.permissions.find(p => p.type === 'anyone');
  useEffect(() => { setAccess(anyone ? 'anyone' : 'restricted'); setLinkRole(anyone?.role || 'reader'); }, [anyone?.id, anyone?.role]);
  const roles = <><option value="reader">{t('viewer')}</option><option value="commenter">{t('commenter')}</option><option value="writer">{t('editor')}</option></>;
  async function mutation(action: () => Promise<unknown>) {
    // Disable khi đang thay quyền, luôn tải lại quyền thật từ Drive sau thành công.
    setBusy(true); try { await action(); await query.refetch(); notify(t('saved')); } finally { setBusy(false); }
  }
  async function applyLink() {
    // Restricted xóa quyền anyone; anyone cập nhật hoặc tạo quyền link duy nhất.
    if (access === 'restricted' && anyone) await api.delete(`${base}/${anyone.id}`);
    if (access === 'anyone') {
      if (anyone) await api.patch(`${base}/${anyone.id}`, { role: linkRole });
      else await api.post(base, { type: 'anyone', role: linkRole });
    }
  }
  return <Modal title={`${t('share')} · ${file!.name}`} onClose={onClose}><div className="modal-body">{query.isPending ? <Loading /> : query.isError ? <p className="error-text">{t(errorCode(query.error), { defaultValue: t('error') })}</p> : <>
    <form onSubmit={event => { event.preventDefault(); void run(() => mutation(async () => { await api.post(base, { type: 'user', email, role, notify: notifyEmail }); setEmail(''); })); }}><div className="invite-row"><input required type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder={t('email')} aria-label={t('email')} /><Select aria-label={t('type')} value={role} onChange={event => setRole(event.target.value)}>{roles}</Select><button className="primary" disabled={busy}>{t('invite')}</button></div><label className="checkbox-label"><input type="checkbox" checked={notifyEmail} onChange={event => setNotifyEmail(event.target.checked)} />{t('notify')}</label></form>
    <h3 className="section-label">{t('people')}</h3><div className="permission-list">{query.data.permissions.filter(p => p.type !== 'anyone').map(permission => <div className="permission-row" key={permission.id}><span className="avatar small-avatar">{(permission.displayName || permission.emailAddress || '?')[0].toUpperCase()}</span><div className="permission-name"><strong>{permission.displayName || permission.emailAddress || permission.type}</strong><span>{permission.emailAddress}</span></div>{permission.role === 'owner' ? <span className="muted small">{t('owner')}</span> : <><Select aria-label={`${t('type')} ${permission.emailAddress}`} disabled={busy} value={permission.role} onChange={event => void run(() => mutation(() => api.patch(`${base}/${permission.id}`, { role: event.target.value })))}>{roles}</Select><button className="text-button danger-text" disabled={busy} onClick={() => void run(() => mutation(() => api.delete(`${base}/${permission.id}`)))}>{t('remove')}</button></>}</div>)}</div>
    <h3 className="section-label">{t('generalAccess')}</h3><div className="general-access">{access === 'restricted' ? <LockKeyhole size={22} /> : <Globe size={22} />}<Select aria-label={t('generalAccess')} value={access} onChange={event => setAccess(event.target.value)}><option value="restricted">{t('restricted')}</option><option value="anyone">{t('anyone')}</option></Select>{access === 'anyone' && <Select aria-label={t('type')} value={linkRole} onChange={event => setLinkRole(event.target.value)}>{roles}</Select>}<button className="secondary" disabled={busy} onClick={() => void run(() => mutation(applyLink))}>{t('save')}</button></div>{access === 'anyone' && linkRole === 'writer' && <p className="warning"><ShieldAlert size={18} />{t('writerWarning')}</p>}
  </>}</div><footer className="modal-footer spread"><button className="secondary" disabled={!query.data} onClick={() => void run(async () => { await navigator.clipboard.writeText(query.data!.url); notify(t('linkCopied')); })}><Copy size={16} />{t('copyLink')}</button><button className="primary" onClick={onDone}>{t('close')}</button></footer></Modal>;
}

// Định dạng chưa có công cụ được giải thích và disable, không báo tải giả thành công.
export function ArchiveDialog({ file, onClose }: DialogProps) {
  const { t } = useTranslation();
  const workspace = useSession(s => s.workspace)!;
  const [format, setFormat] = useState('zip');
  const { run } = useFeedback();
  const query = useQuery({ queryKey: ['archive-formats'], queryFn: async () => (await api.get('/archive-formats')).data.data as Record<string, boolean> });
  return <Modal title={`${t('archive')} · ${file!.name}`} onClose={onClose}><div className="modal-body"><label className="field-label">{t('archiveFormat')}<Select value={format} onChange={event => setFormat(event.target.value)}>{Object.entries(query.data || {}).map(([name, available]) => <option key={name} value={name} disabled={!available}>{name.toUpperCase()}{!available ? ` · ${t('toolMissing')}` : ''}</option>)}</Select></label><p className="muted small">{t('archiveHint')}</p>{query.isError && <p className="error-text">{t('network_error')}</p>}</div><footer className="modal-footer"><button className="secondary" onClick={onClose}>{t('cancel')}</button><button className="primary" disabled={!query.data?.[format]} onClick={() => void run(async () => { await downloadFile(workspace.id, file!.id, `archive?format=${format}`); onClose(); })}><Download size={17} />{t('download')}</button></footer></Modal>;
}

// Lịch sử chỉ hiển thị revision Google còn giữ, phục hồi có xác nhận version hiện tại.
export function HistoryDialog({ file, onClose, onDone }: DialogProps) {
  const { t, i18n } = useTranslation();
  const workspace = useSession(s => s.workspace)!;
  const { run } = useFeedback();
  const base = `/workspaces/${workspace.id}/files/${file!.id}`;
  const query = useQuery({ queryKey: ['revisions', file!.id], queryFn: async () => (await api.get(`${base}/revisions`)).data.data as { native: boolean; url?: string; revisions: { id: string; modifiedTime: string; size?: string }[] } });
  const [busy, setBusy] = useState(false);
  return <Modal title={`${t('history')} · ${file!.name}`} onClose={onClose}><div className="modal-body"><p className="muted small">{t('historyHint')}</p>{query.isPending ? <Loading /> : query.isError ? <p className="error-text">{t(errorCode(query.error), { defaultValue: t('error') })}</p> : query.data.native ? <><p>{t('nativeHistory')}</p><a className="secondary" target="_blank" rel="noreferrer" href={query.data.url}>{t('editGoogle')}</a></> : !query.data.revisions.length ? <Empty title={t('noHistory')} /> : <div className="revision-list">{[...query.data.revisions].reverse().map(revision => <div className="revision-row" key={revision.id}><History size={19} /><div><strong>{t('revision')} {revision.id}</strong><span className="muted small">{fileDate(revision.modifiedTime, i18n.language)} · {fileSize(revision.size)}</span></div><button className="icon-button" aria-label={t('download')} onClick={() => void run(() => downloadFile(workspace.id, file!.id, `revisions/${revision.id}/content`))}><Download size={17} /></button><button className="secondary" disabled={busy} onClick={() => { if (confirm(t('restoreRevision'))) void run(async () => { setBusy(true); try { await api.post(`${base}/revisions/${revision.id}/restore`, { version: file!.version }); onDone(); } finally { setBusy(false); } }); }}>{t('restore')}</button></div>)}</div>}</div></Modal>;
}

// Metadata viewer cho file không hỗ trợ và thao tác thông tin trong menu.
export function DetailsDialog({ file, onClose }: DialogProps) {
  const { t, i18n } = useTranslation();
  return <Modal title={t('details')} onClose={onClose}><div className="modal-body"><div className="detail-title"><FileIcon file={file!} /><h3>{file!.name}</h3></div><dl className="metadata">{[['type', file!.mimeType], ['size', fileSize(file!.size)], ['createdTime', fileDate(file!.createdTime, i18n.language)], ['modifiedTime', fileDate(file!.modifiedTime, i18n.language)]].map(([label, value]) => <div key={label}><dt>{t(label)}</dt><dd>{value}</dd></div>)}</dl></div></Modal>;
}
