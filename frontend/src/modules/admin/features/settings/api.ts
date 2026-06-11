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
  cost_per_1m_input_usd: number;
  cost_per_1m_output_usd: number;
  is_platform_default: boolean;
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
};

export type GeneralSettings = {
  id: number;
  name: string | null;
  tz: string | null;
  language: string | null;
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

export const patchAiKey = (body: { provider: string; api_key?: string; clear?: boolean }) =>
  api('/api/v1/admin/settings/ai/keys', { method: 'PATCH', body: JSON.stringify(body) });

export type TestKeyResult = { ok: boolean; status: string; message: string };

export const testAiKey = (body: { provider: string; api_key: string }) =>
  api<TestKeyResult>('/api/ai/test-key', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams(body).toString(),
  });

export const patchGeneral = (body: Partial<Pick<GeneralSettings, 'name' | 'tz' | 'language'>>) =>
  api('/api/v1/admin/settings/general', { method: 'PATCH', body: JSON.stringify(body) });
