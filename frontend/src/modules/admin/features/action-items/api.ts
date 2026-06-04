import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type ActionItem = {
  id: number;
  group_note_id: number;
  group_name: string;
  text: string;
  assignee_name: string | null;
  due_at: string | null;
  status: 'open' | 'done';
  project_id: number | null;
  created_at: string;
};

export type ActionItemFilters = {
  group_id?: number | null;
  project_id?: number | null;
  done?: boolean | null;
};

function buildParams(filters: ActionItemFilters): string {
  const p = new URLSearchParams();
  if (filters.group_id != null) p.set('group_id', String(filters.group_id));
  if (filters.project_id != null) p.set('project_id', String(filters.project_id));
  if (filters.done != null) p.set('done', String(filters.done));
  const s = p.toString();
  return s ? `?${s}` : '';
}

export const actionItemsQuery = (filters: ActionItemFilters = {}) =>
  queryOptions({
    queryKey: ['admin', 'action-items', filters],
    queryFn: () => api<ActionItem[]>(`/api/v1/admin/action-items${buildParams(filters)}`),
  });

export const patchActionItem = (
  id: number,
  body: { done?: boolean; text?: string; assignee_name?: string | null; project_id?: number | null },
) =>
  api<ActionItem>(`/api/v1/admin/action-items/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
