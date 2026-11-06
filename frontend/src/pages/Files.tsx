import { Select } from '../components/Select';
import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { Search, Plus, Upload, List, Grid2X2, ChevronRight, Home, LockKeyhole, Globe, RefreshCw, X, ArrowDownUp } from 'lucide-react';
import { api, errorCode } from '../services/api';
import { uploadFile } from '../services/upload';
import { useSession } from '../store/session';
import { usePreferences } from '../hooks/usePreferences';
import { Actions, Empty, FileIcon, Loading, useFeedback } from '../components/ui';
import { FOLDER, type DriveFile, type FileList } from '../types';
import { fileDate, fileSize } from '../utils/format';

// Chia sẻ hiển thị ngay tại danh sách bằng quyền có sẵn trong metadata Drive.
function ShareBadge({ file }: { file: DriveFile }) {
  const { t } = useTranslation();
  const publicLink = file.permissions?.some(p => p.type === 'anyone');
  const count = file.permissions?.filter(p => p.role !== 'owner' && p.type !== 'anyone').length || 0;
  return <span className="share-badge" title={t(publicLink ? 'anyone' : 'restricted')}>{publicLink ? <Globe size={13} /> : <LockKeyhole size={13} />}{count > 0 && count}</span>;
}

// Duyệt folder qua query URL để nút Back/Forward và liên kết trực tiếp hoạt động.
export function Files({ onAction }: { onAction: (action: string, file?: DriveFile) => void }) {
  const { t, i18n } = useTranslation();
  const workspace = useSession(s => s.workspace)!;
  const { preferences, update } = usePreferences();
  const [params, setParams] = useSearchParams();
  const folderId = params.get('folder') || workspace.id;
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('name');
  const [direction, setDirection] = useState('asc');
  const [progress, setProgress] = useState<{ name: string; percent: number; index: number; count: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const uploadController = useRef<AbortController | null>(null);
  const dragCount = useRef(0);
  const client = useQueryClient();
  const { run, notify } = useFeedback();
  const query = useQuery({ queryKey: ['files', workspace.id, folderId, search, sort, direction], queryFn: async () => (await api.get(`/workspaces/${workspace.id}/files`, { params: { parent_id: folderId, search, sort, direction } })).data as FileList });
  useEffect(() => () => uploadController.current?.abort(), [workspace.id]);
  useEffect(() => { setSearch(''); }, [folderId]);
  function navigateFolder(id: string) {
    // Giữ Workspace trong URL, chỉ thay folder khi người dùng đi vào breadcrumb.
    setParams({ workspace: workspace.id, folder: id });
  }
  function open(file: DriveFile) { if (file.mimeType === FOLDER) navigateFolder(file.id); else onAction('open', file); }
  async function upload(files: globalThis.FileList | File[]) {
    // Queue tuần tự; mỗi file được chia phần nhỏ, có retry/resume và nút hủy riêng.
    if (progress) return;
    const items = Array.from(files as globalThis.FileList);
    const controller = new AbortController(); uploadController.current = controller;
    try {
      for (const [index, file] of items.entries()) {
        setProgress({ name: file.name, percent: 0, index: index + 1, count: items.length });
        await uploadFile(file, workspace.id, folderId, controller.signal,
          percent => setProgress({ name: file.name, percent, index: index + 1, count: items.length }));
      }
      notify(t('uploaded'));
    } catch (error) {
      // Hủy chủ động không hiện lỗi mạng; lỗi khác vẫn giữ checkpoint để thử tiếp cùng file.
      if (!controller.signal.aborted) throw error;
    } finally { setProgress(null); uploadController.current = null; if (input.current) input.current.value = ''; await client.invalidateQueries({ queryKey: ['files'] }); }
  }
  const actions = (file: DriveFile) => <Actions><button onClick={() => open(file)}>{t('open')}</button><button onClick={() => onAction('share', file)}>{t('share')}</button><button onClick={() => onAction(file.mimeType === FOLDER ? 'archive' : 'download', file)}>{t(file.mimeType === FOLDER ? 'archive' : 'download')}</button><button onClick={() => onAction('rename', file)}>{t('rename')}</button><button onClick={() => onAction('move', file)}>{t('move')}</button>{file.mimeType !== FOLDER && <><button onClick={() => onAction('copy', file)}>{t('copy')}</button><button onClick={() => onAction('history', file)}>{t('history')}</button></>}<button onClick={() => onAction('details', file)}>{t('details')}</button><button className="danger-text" onClick={() => onAction('delete', file)}>{t('delete')}</button></Actions>;
  return <div className="files-page" onDragEnter={event => { event.preventDefault(); if (event.dataTransfer.types.includes('Files')) { dragCount.current++; setDragging(true); } }} onDragOver={event => event.preventDefault()} onDragLeave={event => { event.preventDefault(); if (--dragCount.current <= 0) { setDragging(false); dragCount.current = 0; } }} onDrop={event => { event.preventDefault(); setDragging(false); dragCount.current = 0; void run(() => upload(event.dataTransfer.files)); }}>
    <div className="page-heading"><div><div className="page-eyebrow">{t('workspace')}</div><h1>{workspace.name}</h1></div><div className="row"><button className="secondary" onClick={() => onAction('folderCreate', { id: folderId } as DriveFile)}><Plus size={18} />{t('newFolder')}</button><button className="primary" disabled={!!progress} onClick={() => input.current?.click()}><Upload size={18} />{t('upload')}</button><input hidden ref={input} type="file" multiple onChange={event => { if (event.target.files) void run(() => upload(event.target.files!)); }} /></div></div>
    <nav className="breadcrumbs" aria-label="Breadcrumb"><button onClick={() => navigateFolder(workspace.id)} aria-label={t('home')}><Home size={15} /></button>{query.data?.breadcrumbs.map(file => <span key={file.id}><ChevronRight size={14} /><button onClick={() => navigateFolder(file.id)}>{file.name}</button></span>)}</nav>
    <div className="toolbar"><label className="search"><Search size={18} /><input value={search} onChange={event => setSearch(event.target.value)} placeholder={t('search')} /></label><div className="row"><Select aria-label={t('sort')} value={sort} onChange={event => setSort(event.target.value)}>{['name', 'type', 'size', 'createdTime', 'modifiedTime'].map(key => <option key={key} value={key}>{t(key)}</option>)}</Select><button className="icon-button" aria-label={t(direction === 'asc' ? 'desc' : 'asc')} onClick={() => setDirection(direction === 'asc' ? 'desc' : 'asc')}><ArrowDownUp size={17} /></button><button className="icon-button" onClick={() => void query.refetch()} aria-label={t('refresh')}><RefreshCw size={17} /></button><div className="view-toggle">{(['list', 'grid'] as const).map(view => <button key={view} className={preferences.view === view ? 'active' : ''} aria-label={t(view)} aria-pressed={preferences.view === view} onClick={() => void run(() => update({ view }))}>{view === 'list' ? <List size={17} /> : <Grid2X2 size={17} />}</button>)}</div></div></div>
    {progress && <div className="upload-progress" role="status"><Upload size={18} /><div><span>{t('uploading')} {progress.index}/{progress.count} · {progress.name}</span><progress max={100} value={progress.percent} /></div><strong>{progress.percent}%</strong><button className="icon-button" onClick={() => uploadController.current?.abort()} aria-label={t('cancel')}><X size={18} /></button></div>}
    {query.isPending ? <Loading /> : query.isError ? <Empty title={t(errorCode(query.error), { defaultValue: t('error') })} action={<button className="secondary" onClick={() => void query.refetch()}>{t('retry')}</button>} /> : !query.data.files.length ? <Empty title={t(search ? 'noResults' : 'emptyFolder')} hint={!search ? t('emptyFolderHint') : undefined} /> : preferences.view === 'grid' ?
      <div className="file-grid">{query.data.files.map(file => <article className="file-card" key={file.id}><div className="row spread"><FileIcon file={file} />{actions(file)}</div><button className="file-open" onClick={() => open(file)}><strong>{file.name}</strong><span className="muted small">{fileSize(file.size)}</span></button><div className="row spread small muted"><span>{fileDate(file.modifiedTime, i18n.language)}</span><ShareBadge file={file} /></div></article>)}</div> :
      <div className="table-scroll"><table className="file-table"><thead><tr>{['name', 'type', 'size', 'createdTime', 'modifiedTime'].map(key => <th key={key}><button onClick={() => { setSort(key); setDirection(sort === key && direction === 'asc' ? 'desc' : 'asc'); }}>{t(key)}{sort === key && (direction === 'asc' ? ' ↑' : ' ↓')}</button></th>)}<th><span className="sr-only">{t('actions')}</span></th></tr></thead><tbody>{query.data.files.map(file => <tr key={file.id}><td><div className="row"><button className="file-name" onClick={() => open(file)}><FileIcon file={file} /><span>{file.name}</span></button><ShareBadge file={file} /></div></td><td className="muted type-cell">{file.mimeType === FOLDER ? t('folder') : file.mimeType.startsWith('application/vnd.google-apps') ? file.mimeType.split('.').pop() : file.name.includes('.') ? file.name.split('.').pop()?.toUpperCase() : t('file')}</td><td className="muted">{fileSize(file.size)}</td><td className="muted date-cell">{fileDate(file.createdTime, i18n.language)}</td><td className="muted date-cell">{fileDate(file.modifiedTime, i18n.language)}</td><td>{actions(file)}</td></tr>)}</tbody></table></div>}
    {query.data && <footer className="file-footer">{t('items', { count: query.data.files.length })}<span>{t('drivePowered')}</span></footer>}
    {dragging && <div className="drop-overlay"><Upload size={42} /><h2>{t('dropFiles')}</h2></div>}
  </div>;
}
