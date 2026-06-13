import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Account = {
  id: number;
  email: string;
  name: string | null;
  role: string;
  google_linked: boolean;
  subscription_status: string | null;
  subscription_expiry: string | null;
  cost_cap_usd_daily: number;
};

export type KeyInfo = { present: boolean; last_4?: string };

export type ModelOption = {
  id: number;
  name: string;
  provider: string;
  tier: string;
  capabilities: string[];
  ctx_max: number;
  cost_per_1m_input_usd: number;
  cost_per_1m_output_usd: number;
  is_platform_default: boolean;
  is_own: boolean;
};

export type SlotInfo = {
  slot: 'smart' | 'fast' | 'vision';
  model_id: number | null;
};

export type AiSettings = {
  slots: SlotInfo[];
  keys: Record<string, KeyInfo>;
  models: ModelOption[];
  cost_cap_usd_daily: number;
  provider_urls: Record<string, string>; // base_url của provider custom/self-hosted
};

export type GeneralSettings = {
  id: number;
  name: string | null;
  tz: string | null;
  language: string | null; // ngôn ngữ trợ lý trả lời (vi | en | auto)
  ui_language: string | null; // ngôn ngữ giao diện web (vi | en)
};

export const accountQuery = queryOptions({
  queryKey: ['admin', 'settings', 'account'],
  queryFn: () => api<Account>('/api/v1/admin/settings/account'),
});

export const aiQuery = queryOptions({
  queryKey: ['admin', 'settings', 'ai'],
  queryFn: () => api<AiSettings>('/api/v1/admin/settings/ai'),
});

export const generalQuery = queryOptions({
  queryKey: ['admin', 'settings', 'general'],
  queryFn: () => api<GeneralSettings>('/api/v1/admin/settings/general'),
});

export const patchAccount = (body: { name?: string }) =>
  api('/api/v1/admin/settings/account', { method: 'PATCH', body: JSON.stringify(body) });

export const patchAiSlot = (body: { slot: string; model_id: number | null }) =>
  api('/api/v1/admin/settings/ai', { method: 'PATCH', body: JSON.stringify(body) });

export const patchAiCap = (body: { cost_cap_usd_daily: number }) =>
  api('/api/v1/admin/settings/ai', { method: 'PATCH', body: JSON.stringify(body) });

export const patchAiKey = (body: { provider: string; api_key?: string; clear?: boolean; base_url?: string }) =>
  api('/api/v1/admin/settings/ai/keys', { method: 'PATCH', body: JSON.stringify(body) });

export type TestKeyResult = { ok: boolean; status: string; message: string };

export const testAiKey = (body: { provider: string; api_key: string; base_url?: string }) =>
  api<TestKeyResult>('/api/ai/test-key', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams(body).toString(),
  });

export const patchGeneral = (
  body: Partial<Pick<GeneralSettings, 'name' | 'tz' | 'language' | 'ui_language'>>,
) => api('/api/v1/admin/settings/general', { method: 'PATCH', body: JSON.stringify(body) });

export type ProviderModelsResult = { ok: boolean; models: { id: string }[]; message?: string };

export const listProviderModels = (provider: string) =>
  api<ProviderModelsResult>(`/api/ai/provider-models?provider=${encodeURIComponent(provider)}`);

export const addOwnModel = (body: {
  provider: string;
  name: string;
  tier: string;
  vision?: boolean;
  capabilities?: string[];
  cost_per_1m_input_usd?: number | null;
  cost_per_1m_output_usd?: number | null;
}) =>
  api<{ id: number }>('/api/v1/admin/settings/ai/models', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const patchOwnModel = (
  id: number,
  body: {
    tier?: string;
    capabilities?: string[];
    cost_per_1m_input_usd?: number | null;
    cost_per_1m_output_usd?: number | null;
    ctx_max?: number;
  },
) =>
  api(`/api/v1/admin/settings/ai/models/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });

export const deleteOwnModel = (id: number) =>
  api(`/api/v1/admin/settings/ai/models/${id}`, { method: 'DELETE' });
