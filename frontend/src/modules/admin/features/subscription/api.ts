import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type SubscriptionData = {
  billing_email: string;
  status: string;
  plan: string;
  expires_at: string | null;
  cost_cap_usd_daily: number;
  last_invoice: null;
  upgrade_url: string | null;
};

export const subscriptionQuery = () =>
  queryOptions({
    queryKey: ['admin', 'subscription'],
    queryFn: () => api<SubscriptionData>('/api/v1/admin/subscription'),
  });
