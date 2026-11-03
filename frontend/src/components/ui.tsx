import { useEffect, useRef, type ReactNode, type CSSProperties, createContext, useContext, useState } from 'react';
import { X, LoaderCircle, Folder, FileText, FileCode2, Image, Film, File, Archive, CircleAlert, Check, MoreHorizontal } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { errorCode } from '../services/api';
import { FOLDER, type DriveFile } from '../types';

// Modal native có focus trap/Escape; nội dung tự quyết định giữ hay bỏ thay đổi.
export function Modal({ title, children, onClose, wide = false }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const { t } = useTranslation();
  useEffect(() => { ref.current?.showModal(); return () => ref.current?.close(); }, []);
  return <dialog ref={ref} className={`modal ${wide ? 'wide' : ''}`} onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <header className="modal-header"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label={t('close')}><X size={20} /></button></header>
    {children}
  </dialog>;
}

// Spinner có nhãn đọc được cho công nghệ hỗ trợ.
export function Loading() {
  const { t } = useTranslation();
  return <div className="loading" role="status"><LoaderCircle className="spin" size={22} />{t('loading')}</div>;
}

// Khối trạng thái dùng chung cho empty/error, luôn có đường thử lại khi cần.
export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return <div className="empty"><span className="empty-icon"><Folder size={35} strokeWidth={1.4} /></span><h3>{title}</h3>{hint && <p>{hint}</p>}{action}</div>;
}

// Icon nhận diện MIME Google trước phần mở rộng để Docs/Sheets không có đuôi vẫn đúng loại.
export function FileIcon({ file }: { file: DriveFile }) {
  const mime = file.mimeType;
  const Icon = mime === FOLDER ? Folder : mime.startsWith('image/') ? Image : mime.startsWith('video/') ? Film : /zip|compressed|archive/.test(mime) ? Archive : /javascript|json|python|typescript/.test(mime) || /\.(py|tsx?|jsx?|css|sql|java)$/.test(file.name) ? FileCode2 : /text|document|spreadsheet|presentation|pdf/.test(mime) ? FileText : File;
  return <span className={`file-icon ${mime === FOLDER ? 'folder-icon' : mime.includes('pdf') ? 'pdf-icon' : ''}`}><Icon size={23} strokeWidth={1.7} /></span>;
}

const FeedbackContext = createContext({ notify: (_message: string, _error = false) => {}, run: async (_action: () => Promise<void>) => {} });

// Một lớp bắt lỗi thao tác để mọi nút async đều báo lỗi có thể đọc được.
export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ message: string; error: boolean } | null>(null);
  const { t } = useTranslation();
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(null), 6000); return () => clearTimeout(timer); }, [toast]);
  const notify = (message: string, error = false) => setToast({ message, error });
  async function run(action: () => Promise<void>) {
    // Thao tác gọi API → dịch mã lỗi ổn định, không làm mất nội dung modal đang nhập.
    try { await action(); } catch (error) { notify(t(errorCode(error), { defaultValue: t('unknown_error') }), true); }
  }
  return <FeedbackContext.Provider value={{ notify, run }}>{children}{toast && <div role="status" className={`toast ${toast.error ? 'error' : ''}`}>{toast.error ? <CircleAlert size={19} /> : <Check size={19} />}<span>{toast.message}</span><button className="icon-button" onClick={() => setToast(null)} aria-label={t('close')}><X size={16} /></button></div>}</FeedbackContext.Provider>;
}

// Hook chỉ xuất phần giao tiếp; component không phụ thuộc cấu trúc toast.
export function useFeedback() { return useContext(FeedbackContext); }

// Menu native details hỗ trợ bàn phím; đóng sau khi chọn thao tác.
export function Actions({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDetailsElement>(null);
  const [position, setPosition] = useState<CSSProperties>({});
  useEffect(() => {
    const close = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node)) ref.current?.removeAttribute('open'); };
    document.addEventListener('pointerdown', close); return () => document.removeEventListener('pointerdown', close);
  }, []);
  function positionMenu() {
    // Đặt menu trong viewport để table-scroll không cắt mất nút ở hàng cuối.
    if (!ref.current?.open) return;
    const summary = ref.current.querySelector('summary')!.getBoundingClientRect();
    const menu = ref.current.querySelector('.menu')!.getBoundingClientRect();
    setPosition({ position: 'fixed', right: 'auto', transform: 'none', left: Math.max(12, Math.min(innerWidth - menu.width - 12, summary.right - menu.width)), top: Math.max(12, Math.min(innerHeight - menu.height - 12, summary.bottom + 4)), zIndex: 100 });
  }
  return <details className="actions-menu" ref={ref} onToggle={positionMenu}><summary className="icon-button" aria-label={t('actions')}><MoreHorizontal size={20} /></summary><div className="menu" style={position} onClick={() => ref.current?.removeAttribute('open')}>{children}</div></details>;
}
