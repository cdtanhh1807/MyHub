import { Select } from '../components/Select';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DndContext, PointerSensor, KeyboardSensor, useSensor, useSensors, closestCenter, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, useSortable, arrayMove, sortableKeyboardCoordinates, rectSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Folder, Plus, ArrowUpRight, GripVertical, Search, ArrowDownUp } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '../services/api';
import { usePreferences } from '../hooks/usePreferences';
import { Actions, Empty, useFeedback } from '../components/ui';
import type { DriveFile, Preferences } from '../types';
import { fileDate } from '../utils/format';

interface Props { files: DriveFile[]; onSelect: (file: DriveFile) => void; onAction: (action: string, file?: DriveFile) => void }

// Tên lời chào cố định theo yêu cầu, độc lập profile OAuth và quyền truy cập.
const GREETING_NAME = 'Liam Cao';

// Một thẻ sortable có nút kéo riêng để click mở Workspace không bị nhầm thành drag.
function WorkspaceCard({ file, manual, onSelect, onAction }: { file: DriveFile; manual: boolean; onSelect: Props['onSelect']; onAction: Props['onAction'] }) {
  const { t, i18n } = useTranslation();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: file.id, disabled: !manual });
  return <article ref={setNodeRef} className={`workspace-card ${isDragging ? 'dragging' : ''}`} style={{ transform: CSS.Transform.toString(transform), transition }}>
    <div className="card-top"><span className="workspace-icon"><Folder size={27} strokeWidth={1.5} /></span><div className="row">
      {manual && <button className="icon-button drag-handle" aria-label={t('drag')} {...attributes} {...listeners}><GripVertical size={17} /></button>}
      <Actions><button onClick={() => onAction('workspaceRename', file)}>{t('rename')}</button><button onClick={() => onAction('workspaceDelete', file)} className="danger-text">{t('delete')}</button></Actions>
    </div></div>
    <button className="card-open" onClick={() => onSelect(file)}><h3>{file.name}</h3><span className="muted small">{fileDate(file.createdTime, i18n.language)}</span><ArrowUpRight className="card-arrow" size={20} /></button>
    <footer><span className="dot" />Google Drive<span className="pill">{t('workspace')}</span></footer>
  </article>;
}

// Drive là nguồn danh sách; tìm kiếm cục bộ không sửa dữ liệu nguồn hay thứ tự Mongo.
export function Workspaces({ files, onSelect, onAction }: Props) {
  const { t } = useTranslation();
  const { preferences, update } = usePreferences();
  const [search, setSearch] = useState('');
  const [reordered, setReordered] = useState<DriveFile[] | null>(null);
  const { run } = useFeedback();
  const client = useQueryClient();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 7 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const ordered = preferences.workspace_sort === 'manual' && reordered && reordered.length === files.length && reordered.every(f => files.some(x => x.id === f.id)) ? reordered.map(item => files.find(file => file.id === item.id)!) : files;
  const shown = ordered.filter(file => file.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  async function dragEnd(event: DragEndEvent) {
    // Dnd-kit cung cấp ID → cập nhật thứ tự lạc quan → rollback nếu lưu Mongo lỗi.
    if (!event.over || event.active.id === event.over.id) return;
    const next = arrayMove(ordered, ordered.findIndex(f => f.id === event.active.id), ordered.findIndex(f => f.id === event.over?.id));
    setReordered(next);
    try { await api.put('/workspaces/order', { ids: next.map(f => f.id) }); await client.invalidateQueries({ queryKey: ['workspaces'] }); setReordered(null); }
    catch (error) { setReordered(null); throw error; }
  }
  return <>
    <div className="page-heading workspace-page-heading"><div><h1 className="workspace-greeting">{t('welcome')}, <span>{GREETING_NAME}</span></h1><p>{t('workspaceSubtitle')}</p></div><button className="primary" onClick={() => onAction('workspaceCreate')}><Plus size={18} />{t('newWorkspace')}</button></div>
    <div className="overview-strip"><span className="mini-icon"><Folder size={19} /></span><strong>{files.length}</strong><span>{t('totalWorkspaces')}</span><div className="overview-divider" /><span className="dot" /><span>{t('liveFromDrive')}</span></div>
    <div className="toolbar workspace-toolbar"><label className="search"><Search size={18} /><input value={search} onChange={e => setSearch(e.target.value)} placeholder={t('searchWorkspaces')} /></label><div className="row">
      <Select aria-label={t('sort')} value={preferences.workspace_sort} onChange={e => { setReordered(null); void run(() => update({ workspace_sort: e.target.value as Preferences['workspace_sort'] })); }}><option value="name">{t('nameSort')}</option><option value="date">{t('dateSort')}</option><option value="manual">{t('manual')}</option></Select>
      {preferences.workspace_sort !== 'manual' && <button className="icon-button" aria-label={t(preferences.direction === 'asc' ? 'desc' : 'asc')} onClick={() => void run(() => update({ direction: preferences.direction === 'asc' ? 'desc' : 'asc' }))}><ArrowDownUp size={18} /></button>}
    </div></div>
    {!files.length ? <Empty title={t('emptyWorkspaces')} hint={t('emptyWorkspacesHint')} action={<button className="primary" onClick={() => onAction('workspaceCreate')}><Plus size={18} />{t('newWorkspace')}</button>} /> : !shown.length ? <Empty title={t('noResults')} /> :
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={event => void run(() => dragEnd(event))}><SortableContext items={ordered.map(f => f.id)} strategy={rectSortingStrategy}><div className="workspace-grid">{shown.map(file => <WorkspaceCard key={file.id} file={file} manual={preferences.workspace_sort === 'manual' && !search} onSelect={onSelect} onAction={onAction} />)}<button className="workspace-add" onClick={() => onAction('workspaceCreate')}><span><Plus size={25} /></span>{t('newWorkspace')}</button></div></SortableContext></DndContext>}
  </>;
}
