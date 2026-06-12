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
  subscription_expiry: string | null;
  plan_label: string | null;
  plan_name: string | null;
  active_groups: number;
  active_channels: number;
  last_message_at: string | null;
  tz: string;
  created_at: string | null;
};

export type UsageGauge = { used: number; limit: number | null };

export type BossOverview = {
  id: number;
  email: string;
  name: string | null;
  role: string;
  tz: string | null;
  created_at: string | null;
  subscription: {
    plan_id: number | null;
    plan_name: string | null;
    plan_label: string | null;
    status: string | null;
    expiry: string | null;
    overrides: Record<string, number>;
  };
  usage: {
    groups: UsageGauge;
    tools: UsageGauge;
    channels: UsageGauge;
    mcp: UsageGauge;
    channel_list: { provider: string; display_name: string | null }[];
    cost_today_usd: number;
    cost_cap_usd_daily: number | null;
    cost_30d_usd: number;
    tokens_30d: number;
    msgs_in_30d: number;
    msgs_out_30d: number;
    last_message_at: string | null;
  };
};

export type BossAiSettings = {
  slots: { slot: 'smart' | 'fast' | 'vision'; model_id: number | null }[];
  keys: Record<string, { present: boolean; last_4?: string }>;
  models: {
    id: number;
    name: string;
    provider: string;
    tier: string;
    capabilities: string[];
    is_platform_default: boolean;
    is_own: boolean;
  }[];
  cost_cap_usd_daily: number;
};

export type BossConversation = {
  provider: string;
  chat_id: string;
  chat_type: string;
  title: string;
  msg_count: number;
  last_ts: string | null;
};

export type BossChatMessage = {
  direction: 'in' | 'out';
  id: number;
  sender_name: string | null;
  text: string | null;
  media_kind: string | null;
  media_url: string | null;
  ts: string;
};

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export const bossesQuery = queryOptions({
  queryKey: ['superadmin', 'bosses'] as const,
  queryFn: () => api<Boss[]>('/api/v1/superadmin/bosses'),
});

export const bossOverviewQuery = (id: number) =>
  queryOptions({
    queryKey: ['superadmin', 'boss', id, 'overview'],
    queryFn: () => api<BossOverview>(`/api/v1/superadmin/bosses/${id}/overview`),
  });

export const bossAiQuery = (id: number) =>
  queryOptions({
    queryKey: ['superadmin', 'boss', id, 'ai'],
    queryFn: () => api<BossAiSettings>(`/api/v1/superadmin/bosses/${id}/ai`),
  });

export const bossConversationsQuery = (id: number) =>
  queryOptions({
    queryKey: ['superadmin', 'boss', id, 'conversations'],
    queryFn: () => api<BossConversation[]>(`/api/v1/superadmin/bosses/${id}/conversations`),
  });

export const bossMessages = (
  id: number,
  provider: string,
  chatId: string,
  before?: string | null,
) =>
  api<{ messages: BossChatMessage[]; next_before: string | null }>(
    `/api/v1/superadmin/bosses/${id}/messages?provider=${encodeURIComponent(provider)}` +
      `&chat_id=${encodeURIComponent(chatId)}${before ? `&before=${encodeURIComponent(before)}` : ''}`,
  );

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

export async function patchBossSubscription(
  id: number,
  body: {
    plan_id?: number;
    subscription_status?: string;
    subscription_expiry?: string;
    clear_expiry?: boolean;
    overrides?: Record<string, number | null>;
  },
) {
  return api(`/api/v1/superadmin/bosses/${id}/subscription`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function patchBossAi(
  id: number,
  body: { slot?: string; model_id?: number | null; cost_cap_usd_daily?: number },
) {
  return api(`/api/v1/superadmin/bosses/${id}/ai`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function patchBossAiKey(
  id: number,
  body: { provider: string; api_key?: string; clear?: boolean },
) {
  return api(`/api/v1/superadmin/bosses/${id}/ai/keys`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function addBossOwnModel(
  id: number,
  body: { provider: string; name: string; tier: string; vision?: boolean },
) {
  return api<{ id: number }>(`/api/v1/superadmin/bosses/${id}/ai/models`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function deleteBossOwnModel(id: number, modelId: number) {
  return api(`/api/v1/superadmin/bosses/${id}/ai/models/${modelId}`, { method: 'DELETE' });
}

export async function listBossProviderModels(id: number, provider: string) {
  return api<{ ok: boolean; models: { id: string }[]; message?: string }>(
    `/api/v1/superadmin/bosses/${id}/ai/provider-models?provider=${encodeURIComponent(provider)}`,
  );
}
