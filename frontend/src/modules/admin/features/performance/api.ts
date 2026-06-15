import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type WorkloadAssignee = {
  assignee: string;
  open: number;
  overdue: number;
  done: number;
  total: number;
  completion_rate: number | null;
};

export type OverdueItem = { assignee: string; what: string; due: string };

export type WorkloadData = {
  scope: string;
  totals: { open: number; overdue: number; done: number; assignees: number };
  by_assignee: WorkloadAssignee[];
  overdue_items: OverdueItem[];
};

export const workloadQuery = () =>
  queryOptions({
    queryKey: ['admin', 'workload'],
    queryFn: () => api<WorkloadData>('/api/v1/admin/workload'),
  });
