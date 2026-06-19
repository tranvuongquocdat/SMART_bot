import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type IntegrationStatus = { ok?: boolean; message?: string; checked_at?: string };

export type Integration = {
  provider: string;
  unit_cost_usd: number;
  has_key: boolean;
  status: IntegrationStatus;
  updated_at: string | null;
  count: number;
  cost: number;
};

export type IntegrationUsage = {
  totals: { count: number; cost: number };
  daily: { date: string; count: number; cost_usd: number }[];
};

export const integrationsQuery = () =>
  queryOptions({
    queryKey: ['superadmin', 'integrations'],
    queryFn: () => api<Integration[]>('/api/v1/superadmin/integrations'),
  });

export const integrationUsageQuery = (provider: string, range: number) =>
  queryOptions({
    queryKey: ['superadmin', 'integration-usage', provider, range],
    queryFn: () =>
      api<IntegrationUsage>(`/api/v1/superadmin/integrations/${provider}/usage?range=${range}`),
  });

export const setIntegration = (
  provider: string,
  payload: { api_key?: string; unit_cost_usd?: number },
) =>
  api(`/api/v1/superadmin/integrations/${provider}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });

export const testIntegration = (provider: string) =>
  api<{ ok: boolean; message?: string }>(
    `/api/v1/superadmin/integrations/${provider}/test`,
    { method: 'POST' },
  );
