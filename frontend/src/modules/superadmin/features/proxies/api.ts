import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Proxy = {
  id: number;
  label: string;
  url_masked: string | null;
  region: string | null;
  status: 'active' | 'dead' | 'disabled';
  max_bosses: number;
  assigned_count: number;
  notes: string | null;
  created_at: string | null;
};

export const proxiesQuery = queryOptions({
  queryKey: ['superadmin', 'proxies'] as const,
  queryFn: () => api<Proxy[]>('/api/v1/superadmin/proxies'),
});

export const createProxy = (body: {
  label: string;
  url: string;
  region?: string;
  max_bosses?: number;
  notes?: string;
}) =>
  api<{ id: number }>('/api/v1/superadmin/proxies', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const updateProxy = (
  id: number,
  body: Partial<{
    label: string;
    url: string;
    region: string;
    status: string;
    max_bosses: number;
    notes: string;
  }>,
) =>
  api(`/api/v1/superadmin/proxies/${id}`, { method: 'PATCH', body: JSON.stringify(body) });

export const deleteProxy = (id: number) =>
  api(`/api/v1/superadmin/proxies/${id}`, { method: 'DELETE' });

export const testProxy = (id: number) =>
  api<{ ok: boolean; ip?: string; message?: string }>(
    `/api/v1/superadmin/proxies/${id}/test`,
    { method: 'POST', body: JSON.stringify({}) },
  );

export const setBossProxy = (bossId: number, proxyId: number | null) =>
  api(`/api/v1/superadmin/bosses/${bossId}/proxy`, {
    method: 'PUT',
    body: JSON.stringify({ proxy_id: proxyId }),
  });
