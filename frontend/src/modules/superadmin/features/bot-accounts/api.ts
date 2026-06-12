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

export type BotAccountDetail = {
  id: number;
  provider: string;
  provider_user_id: string;
  display_name: string | null;
  account_kind: string;
  ownership: string | null;
  owner_boss_id: number | null;
  status: string;
  status_reason: string | null;
  max_assigned_bosses: number;
  last_seen_at: string | null;
  msgs_received_total: number;
  msgs_sent_total: number;
  notes: string | null;
  created_at: string | null;
  has_credentials: boolean;
  assignments: {
    boss_id: number;
    boss_email: string;
    boss_name: string | null;
    status: string;
    assigned_at: string | null;
  }[];
};

export type DailyStat = { date: string; received: number; sent: number };

export type QrLoginStatus = {
  status: 'starting' | 'qr' | 'scanned' | 'success' | 'error';
  qr_image_b64: string | null;
  display_name: string | null;
  error: string | null;
  bot_account_id: number | null;
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

export function botAccountDetailQuery(id: number) {
  return queryOptions({
    queryKey: ['superadmin', 'bot-accounts', id, 'detail'] as const,
    queryFn: () => api<BotAccountDetail>(`/api/v1/superadmin/bot-accounts/${id}/detail`),
  });
}

export function botAccountDailyStatsQuery(id: number, days: number) {
  return queryOptions({
    queryKey: ['superadmin', 'bot-accounts', id, 'stats', days] as const,
    queryFn: () =>
      api<DailyStat[]>(`/api/v1/superadmin/bot-accounts/${id}/stats/daily?days=${days}`),
  });
}

export const startAccountQrLogin = (id: number) =>
  api<{ login_id: string; status: string }>(`/api/v1/superadmin/bot-accounts/${id}/qr-login`, {
    method: 'POST',
    body: JSON.stringify({}),
  });

export const accountQrLoginStatus = (loginId: string) =>
  api<QrLoginStatus>(`/api/v1/superadmin/bot-accounts/qr-login/${loginId}`);

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
