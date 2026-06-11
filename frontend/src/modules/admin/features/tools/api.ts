import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Tool = {
  name: string;
  description: string;
  active: boolean;
};

export const toolsQuery = () =>
  queryOptions({
    queryKey: ['admin', 'tools'],
    queryFn: () => api<Tool[]>('/api/v1/admin/tools'),
  });

function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)smart_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

export async function toggleTool(name: string): Promise<{ name: string; active: boolean }> {
  const res = await fetch(`/api/v1/admin/tools/${encodeURIComponent(name)}/toggle`, {
    method: 'PATCH',
    headers: { 'X-CSRF-Token': csrfToken() },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? 'Thao tác thất bại');
  }
  return res.json();
}
