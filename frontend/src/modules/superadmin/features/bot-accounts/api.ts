import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type BotAccount = {
  id: number;
  label: string;
  handle: string;
  channel: string;
  account_kind: string;
  ownership: string | null;
  account_status: string;
  messages_in: number;
  messages_out: number;
  status: 'online' | 'warn' | 'offline';
  last_seen_at: string | null;
};

export type BotMessage = {
  id: number | string;
  text: string;
  direction: 'in' | 'out';
  created_at: string;
};

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export const botAccountsQuery = queryOptions({
  queryKey: ['superadmin', 'bot-accounts', '7d'] as const,
  queryFn: () => api<BotAccount[]>('/api/v1/superadmin/bot-accounts?range=7d'),
});

export function botAccountMessagesQuery(id: number) {
  return queryOptions({
    queryKey: ['superadmin', 'bot-accounts', id, 'messages'] as const,
    queryFn: () => api<BotMessage[]>(`/api/v1/superadmin/bot-accounts/${id}/messages?limit=50`),
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export async function createBotAccount(body: {
  provider: string;
  label: string;
  handle: string;
  account_kind?: string;
  ownership?: string | null;
}) {
  return api<{ id: number }>('/api/v1/superadmin/bot-accounts', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function patchBotAccount(
  id: number,
  body: { label?: string; ownership?: string | null; account_kind?: string },
) {
  return api<{ id: number; ok: boolean }>(`/api/v1/superadmin/bot-accounts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deleteBotAccount(id: number) {
  return api<void>(`/api/v1/superadmin/bot-accounts/${id}`, { method: 'DELETE' });
}
