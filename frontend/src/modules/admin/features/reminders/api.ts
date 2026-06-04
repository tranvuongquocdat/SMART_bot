import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Reminder = {
  id: number;
  text: string;
  due_at: string;
  status: 'pending' | 'done' | 'canceled';
  scope: 'dm' | 'group';
  provider: string | null;
  chat_id: string | null;
  recurring: string | null;
  created_at: string;
};

export const remindersQuery = (status: string = 'pending') =>
  queryOptions({
    queryKey: ['admin', 'reminders', status],
    queryFn: () =>
      api<Reminder[]>(`/api/v1/admin/reminders?status=${encodeURIComponent(status)}`),
  });

export const createReminder = (body: {
  text: string;
  due_at: string;
  scope?: string;
}) => api<Reminder>('/api/v1/admin/reminders', { method: 'POST', body: JSON.stringify(body) });

export const patchReminder = (id: number, body: Partial<Pick<Reminder, 'status' | 'due_at'>>) =>
  api<Reminder>(`/api/v1/admin/reminders/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });

export const deleteReminder = (id: number) =>
  api<void>(`/api/v1/admin/reminders/${id}`, { method: 'DELETE' });
