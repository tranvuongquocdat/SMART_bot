import { queryOptions } from '@tanstack/react-query';
import { api } from './api';

export type Role = 'boss' | 'superadmin';
export type Me = { id: number; roles: Role[] };

export const meQuery = queryOptions({
  queryKey: ['me'] as const,
  queryFn: () => api<Me>('/api/v1/me'),
  staleTime: 60_000,
});
