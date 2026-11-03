import { Children, Fragment, isValidElement, useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown } from 'lucide-react';

interface Choice { value: string; label: string; disabled?: boolean }
interface DropdownProps {
  value: string; options: Choice[]; onValueChange: (value: string) => void;
  className?: string; trigger?: ReactNode; disabled?: boolean; id?: string;
  'aria-label'?: string;
}

// Dropdown dùng chung: menu bo góc theo theme, portal trong dialog để giữ đúng lớp hiển thị.
export function Dropdown({ value, options, onValueChange, className = 'select-control', trigger, disabled, id, 'aria-label': label }: DropdownProps) {
  const generatedId = useId();
  const listId = `${generatedId}-list`;
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const search = useRef({ text: '', time: 0 });
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [position, setPosition] = useState<CSSProperties>({});
  const enabled = options.map((option, index) => option.disabled ? -1 : index).filter(index => index >= 0);
  const selected = options.find(option => option.value === value);
  const unavailable = disabled || !enabled.length;

  function show(last = false) {
    // Mở tại lựa chọn hiện tại; nếu chưa chọn thì bắt đầu từ đầu/cuối theo phím người dùng.
    const index = options.findIndex(option => option.value === value && !option.disabled);
    setActive(index >= 0 ? index : last ? enabled.at(-1)! : enabled[0]);
    setOpen(true);
  }

  function choose(index: number) {
    // Chặn lựa chọn disabled rồi trả ID/value, giữ focus tại control sau khi đóng.
    const option = options[index];
    if (!option || option.disabled) return;
    setOpen(false);
    button.current?.focus({ preventScroll: true });
    onValueChange(option.value);
  }

  function keyDown(event: KeyboardEvent<HTMLButtonElement>) {
    // Hỗ trợ Arrow/Home/End, Enter/Space, Escape, Tab và tìm nhanh bằng bàn phím.
    if (event.key === 'Escape' && open) { event.preventDefault(); event.stopPropagation(); setOpen(false); return; }
    if (event.key === 'Tab') { setOpen(false); return; }
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      if (!open) { show(event.key === 'ArrowUp' || event.key === 'End'); return; }
      const current = enabled.indexOf(active);
      setActive(event.key === 'Home' ? enabled[0] : event.key === 'End' ? enabled.at(-1)! : enabled[(current + (event.key === 'ArrowDown' ? 1 : -1) + enabled.length) % enabled.length]);
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (open) choose(active); else show();
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      const now = Date.now();
      const text = now - search.current.time < 700 ? search.current.text + event.key : event.key;
      search.current = { text, time: now };
      const index = options.findIndex(option => !option.disabled && option.label.toLocaleLowerCase().startsWith(text.toLocaleLowerCase()));
      if (index >= 0) { setActive(index); setOpen(true); }
    }
  }

  useLayoutEffect(() => {
    if (!open || !button.current || !list.current) return;
    function place() {
      // Bám control, lật lên trên khi gần đáy màn hình và không tràn viewport.
      const anchor = button.current!.getBoundingClientRect();
      const menu = list.current!;
      const width = Math.min(Math.max(anchor.width, 176), innerWidth - 24);
      const below = innerHeight - anchor.bottom - 16;
      const above = anchor.top - 16;
      const upwards = below < Math.min(menu.scrollHeight, 180) && above > below;
      const maxHeight = Math.max(60, Math.min(300, upwards ? above : below));
      const height = Math.min(menu.scrollHeight, maxHeight);
      setPosition({ position: 'fixed', width, maxHeight, borderRadius: getComputedStyle(button.current!).borderRadius, left: Math.max(12, Math.min(innerWidth - width - 12, anchor.left)), top: upwards ? Math.max(12, anchor.top - height - 6) : anchor.bottom + 6 });
    }
    place();
    const observer = new ResizeObserver(place);
    observer.observe(button.current);
    const scroll = (event: Event) => { if (!list.current?.contains(event.target as Node)) place(); };
    window.addEventListener('resize', place);
    window.addEventListener('scroll', scroll, true);
    return () => { observer.disconnect(); window.removeEventListener('resize', place); window.removeEventListener('scroll', scroll, true); };
  }, [open, options.length]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!button.current?.contains(event.target as Node) && !list.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);
  useEffect(() => { if (open) document.getElementById(`${listId}-${active}`)?.scrollIntoView({ block: 'nearest' }); }, [open, active, listId]);

  const host = button.current?.closest('dialog') || document.body;
  return <><button ref={button} id={id} type="button" role="combobox" className={className} disabled={!!unavailable} aria-label={label} aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? listId : undefined} aria-activedescendant={open ? `${listId}-${active}` : undefined} onClick={() => open ? setOpen(false) : show()} onKeyDown={keyDown} onBlur={event => { if (!list.current?.contains(event.relatedTarget as Node)) setOpen(false); }}>
    {trigger || <span className="select-value">{selected?.label || value}</span>}<ChevronDown size={15} className="dropdown-chevron" aria-hidden="true" />
  </button>{open && createPortal(<div ref={list} id={listId} role="listbox" aria-label={label} className="dropdown-popup" style={position} onPointerDown={event => { if (event.pointerType === 'mouse') event.preventDefault(); }}>
    {options.map((option, index) => <button id={`${listId}-${index}`} key={option.value} type="button" tabIndex={-1} role="option" aria-selected={option.value === value} aria-disabled={option.disabled || undefined} disabled={option.disabled} className={`dropdown-option ${index === active ? 'highlighted' : ''}`} onPointerMove={event => { if (event.pointerType === 'mouse' && !option.disabled) setActive(index); }} onClick={event => { event.preventDefault(); event.stopPropagation(); choose(index); }}><span>{option.label}</span>{option.value === value && <Check size={16} aria-hidden="true" />}</button>)}
  </div>, host)}</>;
}

interface SelectProps {
  value: string; children: ReactNode; onChange: (event: { target: { value: string } }) => void;
  disabled?: boolean; id?: string; className?: string; 'aria-label'?: string;
}

// Giữ cách khai báo option hiện có, gom mọi select trong app về cùng một dropdown có CSS kiểm soát được.
export function Select({ children, onChange, ...props }: SelectProps) {
  function collect(nodes: ReactNode): Choice[] {
    // React Fragment và mảng option dùng trong Share đều được chuyển thành dữ liệu thuần.
    return Children.toArray(nodes).flatMap(node => {
      if (!isValidElement<{ value?: string; disabled?: boolean; children?: ReactNode }>(node)) return [];
      if (node.type === Fragment) return collect(node.props.children);
      return [{ value: String(node.props.value ?? ''), label: Children.toArray(node.props.children).join(''), disabled: node.props.disabled }];
    });
  }
  return <Dropdown {...props} options={collect(children)} onValueChange={value => { if (value !== props.value) onChange({ target: { value } }); }} />;
}
