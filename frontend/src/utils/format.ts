// Dung lượng native Google không có size nên luôn hiển thị dấu gạch ngang.
export function fileSize(value?: string | null): string {
  if (value == null) return '—';
  const bytes = Number(value);
  if (bytes < 1024) return `${bytes} B`;
  const index = Math.min(3, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** index).toFixed(1)} ${['B', 'KB', 'MB', 'GB'][index]}`;
}

// Dùng timezone trình duyệt để các thiết bị hiển thị thời gian quen thuộc.
export function fileDate(value: string | undefined, language: string): string {
  return value ? new Intl.DateTimeFormat(language === 'vi' ? 'vi-VN' : 'en-US', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—';
}
