import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type SAPlan = {
  id: number;
  name: string;
  label: string;
  limits_json: string;
  is_active: boolean;
  sort_order: number;
};

export type PlanLimits = {
  max_active_groups?: number | null;
  max_active_tools?: number | null;
  max_active_channels?: number | null;
  mcp_slots?: number | null;
  duration_days?: number | null;
  cost_cap_usd_daily?: number | null;
};

export const plansAdminQuery = () =>
  queryOptions({
    queryKey: ['superadmin', 'plans'],
    queryFn: () => api<SAPlan[]>('/api/v1/superadmin/plans'),
  });

function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)smart_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

async function jsonMutation(url: string, method: string, body: object): Promise<unknown> {
  const res = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrfToken(),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? 'Thao tác thất bại');
  }
  return res.json();
}

export function createPlan(payload: {
  name: string;
  label: string;
  limits_json: PlanLimits;
  sort_order?: number;
}) {
  return jsonMutation('/api/v1/superadmin/plans', 'POST', payload);
}

export function updatePlan(
  id: number,
  payload: Partial<{ label: string; limits_json: PlanLimits; is_active: boolean; sort_order: number }>,
) {
  return jsonMutation(`/api/v1/superadmin/plans/${id}`, 'PATCH', payload);
}
