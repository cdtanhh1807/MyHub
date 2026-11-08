import { useEffect, useMemo, useRef, useState, type ComponentType } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import CodeMirror from '@uiw/react-codemirror';
import { languages } from '@codemirror/language-data';
import type { Extension } from '@codemirror/state';
import { Document, Page, pdfjs } from 'react-pdf';
import { ZoomIn, ZoomOut, ChevronLeft, ChevronRight, ExternalLink, Save, Download } from 'lucide-react';
import { api, mediaUrl, downloadFile, errorCode } from '../../services/api';
import { useSession } from '../../store/session';
import { Modal, Loading, FileIcon, useFeedback } from '../../components/ui';
import { fileDate, fileSize } from '../../utils/format';
import type { DriveFile } from '../../types';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

// Worker được Vite đóng gói cục bộ; không phụ thuộc CDN bên ngoài để đọc PDF cá nhân.
pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString();

interface ViewerProps {
  file: DriveFile; workspaceId: string; url: string; previewUrl: string; editUrl: string; siblings: DriveFile[];
  setDirty: (dirty: boolean) => void; onChanged: () => void; onSelect: (file: DriveFile) => void; onClose: () => void;
}

// PDF viewer dùng chung cho PDF gốc và PDF Office, có chuyển trang/zoom.
function PdfViewer({ url }: ViewerProps) {
  const { t } = useTranslation();
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [scale, setScale] = useState(1);
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  const source = useMemo(() => ({ url, withCredentials: true }), [url]);
  useEffect(() => {
    const observer = new ResizeObserver(entries => setWidth(Math.max(200, entries[0].contentRect.width - 32)));
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  return <div className="pdf-viewer" ref={container}><div className="viewer-toolbar"><button className="icon-button" disabled={page <= 1} aria-label={t('previous')} onClick={() => setPage(page - 1)}><ChevronLeft size={19} /></button><span>{t('page')} {page} / {pages || '—'}</span><button className="icon-button" disabled={page >= pages} aria-label={t('next')} onClick={() => setPage(page + 1)}><ChevronRight size={19} /></button><span className="separator" /><button className="icon-button" aria-label={t('zoomOut')} disabled={scale <= 0.5} onClick={() => setScale(scale - .25)}><ZoomOut size={19} /></button><span>{Math.round(scale * 100)}%</span><button className="icon-button" aria-label={t('zoomIn')} disabled={scale >= 3} onClick={() => setScale(scale + .25)}><ZoomIn size={19} /></button></div><div className="pdf-pages"><Document file={source} onLoadSuccess={({ numPages }) => { setPages(numPages); setPage(1); }} loading={<Loading />} error={<p className="error-text">{t('unknown_error')}</p>}><Page pageNumber={page} width={Math.min(width, 900)} scale={scale} loading={<Loading />} /></Document></div></div>;
}

// Ảnh dùng URL stream gốc; prev/next chỉ duyệt ảnh trong folder đang xem.
function ImageViewer({ file, url, siblings, onSelect }: ViewerProps) {
  const { t } = useTranslation();
  const [scale, setScale] = useState(1);
  const images = siblings.filter(item => item.mimeType.startsWith('image/'));
  const index = images.findIndex(item => item.id === file.id);
  useEffect(() => setScale(1), [file.id]);
  return <><div className="viewer-toolbar"><button className="icon-button" disabled={index <= 0} aria-label={t('previous')} onClick={() => onSelect(images[index - 1])}><ChevronLeft size={19} /></button><span>{index + 1} / {images.length || 1}</span><button className="icon-button" disabled={index < 0 || index >= images.length - 1} aria-label={t('next')} onClick={() => onSelect(images[index + 1])}><ChevronRight size={19} /></button><span className="separator" /><button className="icon-button" aria-label={t('zoomOut')} onClick={() => setScale(Math.max(.25, scale - .25))}><ZoomOut size={19} /></button><button className="icon-button" aria-label={t('zoomIn')} onClick={() => setScale(Math.min(4, scale + .25))}><ZoomIn size={19} /></button></div><div className="image-stage"><img src={url} alt={file.name} style={{ width: `${scale * 100}%`, maxWidth: `${scale * 100}%` }} /></div></>;
}

// Trình phát HTML5 tự gửi Range, backend chuyển tiếp status/content-range từ Drive.
function VideoViewer({ url }: ViewerProps) { return <div className="media-stage"><video src={url} controls preload="metadata" /></div>; }
// Âm thanh dùng cùng đường truyền có cookie giới hạn file như video.
function AudioViewer({ url }: ViewerProps) { return <div className="media-stage"><audio src={url} controls preload="metadata" /></div>; }

// Google /preview dùng phiên Google trong browser, nút mở tab mới luôn có sẵn khi iframe không tải.
function DriveViewer({ previewUrl, editUrl, file }: ViewerProps) {
  const { t } = useTranslation();
  return <><p className="viewer-note">{t('drivePreviewHint')} <a href={editUrl} target="_blank" rel="noreferrer">{t('editGoogle')} <ExternalLink size={13} /></a></p><iframe key={`${file.id}:${file.version}`} className="drive-frame" title={t('preview')} src={previewUrl} allow="autoplay; fullscreen" referrerPolicy="no-referrer" /></>;
}

// Office thử PDF trước; có fallback tự động khi lỗi và nút chuyển thủ công nếu phân trang xấu.
function OfficeViewer(props: ViewerProps) {
  const { t } = useTranslation();
  const [fallback, setFallback] = useState(false);
  const query = useQuery({ queryKey: ['office-pdf', props.file.id, props.file.version], queryFn: async () => {
    const response = await api.get(`/workspaces/${props.workspaceId}/files/${props.file.id}/pdf`, { responseType: 'blob' });
    return URL.createObjectURL(response.data);
  }, retry: false, gcTime: 0 });
  useEffect(() => () => { if (query.data) URL.revokeObjectURL(query.data); }, [query.data]);
  if (fallback || query.isError) return <DriveViewer {...props} />;
  return <><div className="viewer-note"><button className="text-button" onClick={() => setFallback(true)}>{t('fallback')}</button></div>{query.isPending ? <Loading /> : <PdfViewer {...props} url={query.data} />}</>;
}

// Editor chỉ chứa text nhỏ đã kiểm tra phía server; luôn giữ nội dung khi save thất bại.
function TextViewer({ file, workspaceId, setDirty, onChanged, onClose }: ViewerProps) {
  const { t } = useTranslation();
  const { run, notify } = useFeedback();
  const [content, setContent] = useState('');
  const [original, setOriginal] = useState('');
  const [version, setVersion] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');
  const [conflict, setConflict] = useState(false);
  const [extensions, setExtensions] = useState<Extension[]>([]);
  const theme = useSession(s => s.preferences.theme);
  const base = `/workspaces/${workspaceId}/files/${file.id}/text`;
  const dirty = loaded && content !== original;
  async function load() {
    // Tải lại có chủ đích; nếu API lỗi, nội dung người dùng đang sửa vẫn được giữ.
    const response = await api.get(base);
    setContent(response.data.data.content); setOriginal(response.data.data.content); setVersion(response.data.data.version); setLoaded(true); setConflict(false); setFailure('');
  }
  useEffect(() => { let active = true; void load().catch(error => { if (active) setFailure(errorCode(error)); }); return () => { active = false; }; }, [base]);
  useEffect(() => { setDirty(dirty); }, [dirty, setDirty]);
  useEffect(() => {
    // Metadata được đồng bộ từ thiết bị khác: chỉ tải nội dung mới khi không có bản nháp.
    if (!loaded || busy || !file.version || file.version === version) return;
    // Metadata cũ có thể về chậm sau lần tự lưu; không xem version thấp hơn là xung đột mới.
    if (/^\d+$/.test(file.version) && /^\d+$/.test(version) && BigInt(file.version) <= BigInt(version)) return;
    if (dirty) { setConflict(true); return; }
    let active = true;
    void api.get(base).then(({ data }) => {
      if (!active) return;
      setContent(data.data.content); setOriginal(data.data.content); setVersion(data.data.version); setFailure('');
    }).catch(error => { if (active) setFailure(errorCode(error)); });
    return () => { active = false; };
  }, [file.version, version, loaded, busy, dirty, base]);
  useEffect(() => {
    const language = languages.find(item => item.extensions.includes(file.name.split('.').pop() || ''));
    void language?.load().then(extension => setExtensions([extension]));
  }, [file.name]);
  async function save(strategy = 'normal') {
    // Version gửi kèm nội dung; conflict không ghi đè cho tới khi người dùng chọn rõ chiến lược.
    setBusy(true);
    try {
      const response = await api.put(base, { content, version, strategy });
      setOriginal(content); setVersion(response.data.version); setConflict(false); setDirty(false); onChanged(); notify(t('saved'));
      if (strategy === 'copy') onClose();
    } catch (error) { if (errorCode(error) === 'conflict') setConflict(true); else throw error; }
    finally { setBusy(false); }
  }
  if (failure) return <div className="modal-body error-text">{t(failure, { defaultValue: t('error') })}</div>;
  if (!loaded) return <Loading />;
  return <div onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); if (!busy) void run(() => save()); } }}>
    <div className="viewer-toolbar"><span className="muted small">UTF-8 · {file.name.split('.').pop()?.toUpperCase()}</span><span className="unsaved-label">{dirty && t('unsaved')}</span><button className="primary" disabled={busy || !dirty} onClick={() => void run(() => save())}><Save size={16} />{t(busy ? 'loading' : 'save')}</button></div>
    {conflict && <div className="conflict-box"><strong>{t('conflictTitle')}</strong><p>{t('conflictHint')}</p><div className="row wrap"><button className="secondary" disabled={busy} onClick={() => { if (confirm(t('discard'))) void run(load); }}>{t('reload')}</button><button className="primary" disabled={busy} onClick={() => void run(() => save('copy'))}>{t('saveCopy')}</button><button className="danger" disabled={busy} onClick={() => void run(() => save('overwrite'))}>{t('overwrite')}</button></div></div>}
    <CodeMirror value={content} height="62vh" extensions={extensions} theme={theme === 'dark' || document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'} onChange={setContent} basicSetup={{ lineNumbers: true, foldGutter: true, highlightActiveLine: true }} />
  </div>;
}

// Loại chưa có viewer vẫn có metadata/download, không cố mở nội dung nhị phân trong editor.
function MetadataViewer({ file }: ViewerProps) {
  const { t, i18n } = useTranslation();
  return <div className="modal-body metadata-viewer"><FileIcon file={file} /><h3>{file.name}</h3><p>{t('unsupported')}</p><dl className="metadata">{[['type', file.mimeType], ['size', fileSize(file.size)], ['modifiedTime', fileDate(file.modifiedTime, i18n.language)]].map(([key, value]) => <div key={key}><dt>{t(key)}</dt><dd>{value}</dd></div>)}</dl></div>;
}

// Bảng đăng ký viewer tập trung: thêm loại mới không cần thay AppShell hay trang Files.
const VIEWERS: Record<string, ComponentType<ViewerProps>> = { pdf: PdfViewer, office: OfficeViewer, image: ImageViewer, video: VideoViewer, audio: AudioViewer, drive: DriveViewer, text: TextViewer, metadata: MetadataViewer };

export default function Viewer({ file, siblings, onClose, onChanged, onSelect }: { file: DriveFile; siblings: DriveFile[]; onClose: () => void; onChanged: () => void; onSelect: (file: DriveFile) => void }) {
  const { t } = useTranslation();
  const workspace = useSession(s => s.workspace)!;
  const { run } = useFeedback();
  const [dirty, setDirty] = useState(false);
  const metadata = useQuery({ queryKey: ['metadata', workspace.id, file.id], queryFn: async () => (await api.get(`/workspaces/${workspace.id}/files/${file.id}`)).data as DriveFile });
  const current = metadata.data || file;
  const query = useQuery({ queryKey: ['viewer', workspace.id, file.id], queryFn: async () => {
    const [{ data }, url] = await Promise.all([api.get(`/workspaces/${workspace.id}/files/${file.id}/preview`), mediaUrl(workspace.id, file.id, 'content?inline=true')]);
    return { ...data.data, url } as { kind: string; preview_url: string; edit_url: string; url: string };
  }, staleTime: 0 });
  useEffect(() => {
    // Khi tab viewer sống lâu, làm mới cookie media trước khi nó hết hạn để video còn tua được.
    const renew = () => { void mediaUrl(workspace.id, file.id).catch(() => {}); };
    const timer = setInterval(renew, 20 * 60 * 1000);
    window.addEventListener('myhub:session-refreshed', renew);
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => { clearInterval(timer); window.removeEventListener('myhub:session-refreshed', renew); window.removeEventListener('beforeunload', warn); };
  }, [workspace.id, file.id, dirty]);
  function close() { if (!dirty || confirm(t('discard'))) onClose(); }
  // Giữ loại editor khi đang có bản nháp, kể cả khi thiết bị khác đổi MIME của file.
  const kind = useRef('metadata');
  if (!dirty && query.data?.kind) kind.current = query.data.kind;
  const Component = VIEWERS[kind.current] || MetadataViewer;
  return <Modal title={current.name} wide onClose={close}><div className="viewer-actions"><span className="pill">{t('preview')}</span><div className="row"><a className="text-button" href={query.data?.edit_url || file.webViewLink} target="_blank" rel="noreferrer"><ExternalLink size={15} />{t('editGoogle')}</a><button className="secondary" onClick={() => void run(() => downloadFile(workspace.id, file.id))}><Download size={15} />{t('download')}</button></div></div>{metadata.isError && <p role="alert" className="modal-body error-text">{t(errorCode(metadata.error), { defaultValue: t('error') })}</p>}{query.isPending ? <Loading /> : query.isError && !query.data ? <p className="modal-body error-text">{t(errorCode(query.error), { defaultValue: t('error') })}</p> : <Component key={file.id} file={current} workspaceId={workspace.id} url={`${query.data.url}&version=${encodeURIComponent(current.version || '')}`} previewUrl={query.data.preview_url} editUrl={query.data.edit_url} siblings={siblings} setDirty={setDirty} onChanged={onChanged} onSelect={onSelect} onClose={onClose} />}</Modal>;
}
