import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type PromptRow = {
  id: number;
  key: string;
  version: number;
  is_active: boolean;
  notes: string | null;
  created_at: string | null;
};

export type PromptDetail = PromptRow & {
  body: string;
  created_by: number | null;
};

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export const promptsQuery = queryOptions({
  queryKey: ['superadmin', 'prompts'] as const,
  queryFn: () => api<PromptRow[]>('/api/v1/superadmin/prompts'),
});

export function promptDetailQuery(id: number) {
  return queryOptions({
    queryKey: ['superadmin', 'prompts', id] as const,
    queryFn: () => api<PromptDetail>(`/api/v1/superadmin/prompts/${id}`),
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export async function createPrompt(body: { key: string; body: string; notes?: string | null }) {
  return api<{ id: number }>('/api/v1/superadmin/prompts', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function patchPrompt(
  id: number,
  body: { body?: string; notes?: string | null; is_active?: boolean },
) {
  return api<{ id: number; ok: boolean }>(`/api/v1/superadmin/prompts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deletePrompt(id: number) {
  return api<void>(`/api/v1/superadmin/prompts/${id}`, { method: 'DELETE' });
}
