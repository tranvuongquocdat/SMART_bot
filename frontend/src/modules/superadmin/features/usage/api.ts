import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type PlatformUsage = {
  range_days: number;
  totals: {
    tokens_in: number;
    tokens_out: number;
    tokens: number;
    calls: number;
    cost_usd: number;
  };
  daily: { day: string; tokens: number; calls: number; cost_usd: number }[];
  by_boss: {
    boss_id: number;
    email: string;
    name: string | null;
    tokens: number;
    calls: number;
    cost_usd: number;
  }[];
  by_feature: { feature: string; tokens: number; calls: number; cost_usd: number }[];
};

export const platformUsageQuery = (range: string) =>
  queryOptions({
    queryKey: ['superadmin', 'usage', range],
    queryFn: () => api<PlatformUsage>(`/api/v1/superadmin/usage?range=${range}`),
  });
