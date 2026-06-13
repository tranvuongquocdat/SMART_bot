import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type UsageTotals = {
  tokens_in: number;
  tokens_out: number;
  tokens: number;
  messages: number;
  cost_usd: number;
};

export type UsageDayRow = {
  date: string;
  tokens_in: number;
  tokens_out: number;
  tokens: number;
  messages: number;
  cost_usd: number;
};

export type UsageModelRow = {
  provider: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  calls: number;
  cost_usd: number;
};

export type UsageData = {
  range_days: number;
  totals: UsageTotals;
  daily: UsageDayRow[];
  by_model: UsageModelRow[];
};

export const usageQuery = (range: string = '30d') =>
  queryOptions({
    queryKey: ['admin', 'usage', range],
    queryFn: () => api<UsageData>(`/api/v1/admin/usage?range=${encodeURIComponent(range)}`),
  });
