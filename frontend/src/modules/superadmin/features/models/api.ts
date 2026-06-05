import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Slot = {
  slot: 'smart' | 'fast' | 'vision';
  model_id: number | null;
  model: string | null;
  provider: string | null;
  status: 'active' | 'fallback' | 'missing';
};

export type Model = {
  id: number;
  name: string;
  provider: string;
  endpoint_kind: string;
  base_url: string | null;
  tier: string;
  ctx_max: number;
  capabilities: string[];
  cost_per_1m_input_usd: number | null;
  cost_per_1m_output_usd: number | null;
  is_platform_default: boolean;
  is_active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type LlmRoute = {
  id: number;
  feature: string;
  condition_cel: string | null;
  target_tier: string;
  fallback_chain: unknown[];
  weight: number;
  is_active: boolean;
  notes: string | null;
  updated_at: string;
};

export type FeatureBudget = {
  feature: string;
  max_input_tokens: number;
  max_output_tokens: number;
  trim_policy_json: unknown;
  compression_strategy: string;
  cache_prefix_hint: string | null;
  updated_at: string;
};

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

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export const slotsQuery = queryOptions({
  queryKey: ['superadmin', 'model-slots'] as const,
  queryFn: () => api<Slot[]>('/api/v1/superadmin/model-slots'),
});

export const modelsQuery = queryOptions({
  queryKey: ['superadmin', 'models'] as const,
  queryFn: () => api<Model[]>('/api/v1/superadmin/models'),
});

export const llmRoutesQuery = queryOptions({
  queryKey: ['superadmin', 'llm-routes'] as const,
  queryFn: () => api<LlmRoute[]>('/api/v1/superadmin/llm-routes'),
});

export const featureBudgetsQuery = queryOptions({
  queryKey: ['superadmin', 'feature-budgets'] as const,
  queryFn: () => api<FeatureBudget[]>('/api/v1/superadmin/feature-budgets'),
});

export const botAccountsQuery = queryOptions({
  queryKey: ['superadmin', 'bot-accounts', '7d'] as const,
  queryFn: () => api<BotAccount[]>('/api/v1/superadmin/bot-accounts?range=7d'),
});

// ---------------------------------------------------------------------------
// Mutations helpers
// ---------------------------------------------------------------------------

export async function patchModelSlot(slot: string, modelId: number) {
  return api<{ slot: string; model_id: number; model: string }>(
    `/api/v1/superadmin/model-slots/${slot}`,
    { method: 'PATCH', body: JSON.stringify({ model_id: modelId }) },
  );
}

export async function createModel(body: {
  name: string;
  provider: string;
  tier: string;
  endpoint_kind?: string;
  base_url?: string | null;
  ctx_max?: number;
  capabilities?: string[];
  cost_per_1m_input_usd?: number | null;
  cost_per_1m_output_usd?: number | null;
  is_platform_default?: boolean;
  is_active?: boolean;
  notes?: string | null;
}) {
  return api<{ id: number }>('/api/v1/superadmin/models', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function patchModel(
  id: number,
  body: Partial<Pick<Model, 'tier' | 'ctx_max' | 'cost_per_1m_input_usd' | 'cost_per_1m_output_usd' | 'is_platform_default' | 'is_active' | 'notes'>>,
) {
  return api<{ id: number; ok: boolean }>(`/api/v1/superadmin/models/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deleteModel(id: number) {
  return api<void>(`/api/v1/superadmin/models/${id}`, { method: 'DELETE' });
}

export async function patchLlmRoute(
  id: number,
  body: Partial<Pick<LlmRoute, 'target_tier' | 'fallback_chain' | 'weight' | 'is_active' | 'notes'>>,
) {
  return api<{ id: number; ok: boolean }>(`/api/v1/superadmin/llm-routes/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function patchFeatureBudget(
  feature: string,
  body: Partial<Pick<FeatureBudget, 'max_input_tokens' | 'max_output_tokens' | 'compression_strategy' | 'cache_prefix_hint'>>,
) {
  return api<{ feature: string; ok: boolean }>(`/api/v1/superadmin/feature-budgets/${feature}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}
