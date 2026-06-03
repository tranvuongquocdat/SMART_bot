const RTF = new Intl.RelativeTimeFormat('vi', { numeric: 'auto' });

export function relativeTime(iso: string | null): string {
  if (!iso) return '—';
  const diffMs = new Date(iso).getTime() - Date.now();
  const minutes = Math.round(diffMs / 60_000);
  if (Math.abs(minutes) < 60) return RTF.format(minutes, 'minute');
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return RTF.format(hours, 'hour');
  const days = Math.round(hours / 24);
  return RTF.format(days, 'day');
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat('vi-VN').format(n);
}
