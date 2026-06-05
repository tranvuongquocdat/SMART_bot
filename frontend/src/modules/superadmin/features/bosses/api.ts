import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Boss = {
  id: number;
  email: string;
  name: string | null;
  role: 'boss' | 'superadmin';
  subscription_status: string;
  tz: string;
  created_at: string | null;
};

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export const bossesQuery = queryOptions({
  queryKey: ['superadmin', 'bosses'] as const,
  queryFn: () => api<Boss[]>('/api/v1/superadmin/bosses'),
});

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export async function createBoss(body: {
  email: string;
  name?: string | null;
  role: string;
}) {
  return api<{ id: number }>('/api/v1/superadmin/bosses', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function patchBoss(
  id: number,
  body: { name?: string | null; role?: string; tz?: string },
) {
  return api<{ id: number; ok: boolean }>(`/api/v1/superadmin/bosses/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deleteBoss(id: number) {
  return api<void>(`/api/v1/superadmin/bosses/${id}`, { method: 'DELETE' });
}
