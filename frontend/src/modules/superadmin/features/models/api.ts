import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Slot = {
  slot: 'smart' | 'fast' | 'vision';
  model: string | null;
  provider: string | null;
  status: 'active' | 'fallback' | 'missing';
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

export const slotsQuery = queryOptions({
  queryKey: ['superadmin', 'model-slots'] as const,
  queryFn: () => api<Slot[]>('/api/v1/superadmin/model-slots'),
});

export const botAccountsQuery = queryOptions({
  queryKey: ['superadmin', 'bot-accounts', '7d'] as const,
  queryFn: () => api<BotAccount[]>('/api/v1/superadmin/bot-accounts?range=7d'),
});
