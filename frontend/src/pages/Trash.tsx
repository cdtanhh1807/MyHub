import { Select } from '../components/Select';
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { RotateCcw, Trash2 } from 'lucide-react';
import { api, errorCode } from '../services/api';
import { useSession } from '../store/session';
import { Loading, Empty, FileIcon, useFeedback } from '../components/ui';
import type { FileList } from '../types';

// Thùng rác toàn bộ hoặc từng Workspace; mỗi mục mang ID Workspace để restore đúng cây.
export function Trash() {
  const { t } = useTranslation();
  const workspace = useSession(s => s.workspace);
  const [scope, setScope] = useState('');
  const { run, notify } = useFeedback();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ['trash', scope], queryFn: async () => (await api.get(scope ? `/workspaces/${scope}/trash` : '/trash')).data as FileList });
  const workspaces = useQuery({ queryKey: ['workspaces'], queryFn: async () => (await api.get('/workspaces')).data as FileList });
  const allTrash = useQuery({ queryKey: ['trash', ''], queryFn: async () => (await api.get('/trash')).data as FileList });
  // Bao gồm Workspace còn hoạt động lẫn Workspace đã xóa, không giới hạn ở Workspace đang chọn.
  const options = new Map((workspaces.data?.files || []).map(file => [file.id, file.name]));
  for (const file of allTrash.data?.files || []) if (file.workspace_id) options.set(file.workspace_id, file.workspace_name || file.workspace_id);
  if (workspace && !options.has(workspace.id)) options.set(workspace.id, workspace.name);
  return <><div className="page-heading"><div><div className="page-eyebrow"><Trash2 size={15} />MYHUB</div><h1>{t('trash')}</h1><p>{t('trashHint')}</p></div></div><div className="toolbar"><Select aria-label={t('workspace')} value={scope} onChange={event => setScope(event.target.value)}><option value="">{t('allWorkspaces')}</option>{[...options].map(([id, name]) => <option key={id} value={id}>{name}</option>)}</Select></div>
    {query.isPending ? <Loading /> : query.isError ? <Empty title={t(errorCode(query.error), { defaultValue: t('error') })} /> : !query.data.files.length ? <Empty title={t('trashEmpty')} /> : <div className="trash-list">{query.data.files.map(file => <article className="trash-row" key={file.id}><FileIcon file={file} /><div className="trash-name"><strong>{file.name}</strong><span className="muted small">{file.workspace_name}</span></div><button className="secondary" onClick={() => void run(async () => { const workspaceId = file.workspace_id || scope || file.id; await api.post(`/workspaces/${workspaceId}/files/${file.id}/restore`); notify(t('restored')); await client.invalidateQueries(); })}><RotateCcw size={16} />{t('restore')}</button></article>)}</div>}</>;
}
