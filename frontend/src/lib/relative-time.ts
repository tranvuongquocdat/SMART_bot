// Thời gian tương đối dùng khóa i18n (time.secAgo/minAgo/hourAgo/dayAgo).
type T = (key: string, vars?: Record<string, string | number>) => string;

export function relativeTimeT(iso: string, t: T): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return t('time.secAgo', { n: s });
  const m = Math.floor(s / 60);
  if (m < 60) return t('time.minAgo', { n: m });
  const h = Math.floor(m / 60);
  if (h < 24) return t('time.hourAgo', { n: h });
  return t('time.dayAgo', { n: Math.floor(h / 24) });
}
