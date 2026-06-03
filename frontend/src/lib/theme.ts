const KEY = 'smart_theme';

export type Theme = 'dark' | 'light';

export function getTheme(): Theme {
  return (localStorage.getItem(KEY) as Theme) || 'dark';
}

export function applyTheme(t: Theme) {
  document.documentElement.classList.toggle('light', t === 'light');
  localStorage.setItem(KEY, t);
}

export function initTheme() {
  applyTheme(getTheme());
}

export function toggleTheme() {
  applyTheme(getTheme() === 'dark' ? 'light' : 'dark');
}
