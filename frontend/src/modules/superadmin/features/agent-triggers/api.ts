import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AgentTrigger = {
  id: number;
  op_name: string;
  event_name: string;
  debounce_json: Record<string, unknown> | null;
  threshold_json: Record<string, unknown> | null;
  enabled: boolean;
  updated_at: string | null;
};

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export const agentTriggersQuery = queryOptions({
  queryKey: ['superadmin', 'agent-triggers'] as const,
  queryFn: () => api<AgentTrigger[]>('/api/v1/superadmin/agent-triggers'),
});

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export async function createAgentTrigger(body: {
  op_name: string;
  event_name: string;
  debounce_json?: Record<string, unknown> | null;
  threshold_json?: Record<string, unknown> | null;
  enabled?: boolean;
}) {
  return api<{ id: number }>('/api/v1/superadmin/agent-triggers', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function patchAgentTrigger(
  id: number,
  body: {
    enabled?: boolean;
    debounce_json?: Record<string, unknown> | null;
    threshold_json?: Record<string, unknown> | null;
  },
) {
  return api<{ id: number; ok: boolean }>(`/api/v1/superadmin/agent-triggers/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deleteAgentTrigger(id: number) {
  return api<void>(`/api/v1/superadmin/agent-triggers/${id}`, { method: 'DELETE' });
}
