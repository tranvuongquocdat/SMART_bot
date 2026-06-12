import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Notification = {
  id: number;
  kind: 'announcement' | 'subscription' | 'system';
  title: string;
  body: string | null;
  link: string | null;
  created_at: string;
  is_read: boolean;
};

export type NotificationFeed = { items: Notification[]; unread_count: number };

export const notificationsQuery = queryOptions({
  queryKey: ['me', 'notifications'] as const,
  queryFn: () => api<NotificationFeed>('/api/v1/me/notifications'),
  // Poll nhẹ để chuông cập nhật khi có thông báo mới (vd gói được duyệt).
  refetchInterval: 60_000,
});

export const markNotificationsRead = (id?: number) =>
  api<{ marked: number }>('/api/v1/me/notifications/read', {
    method: 'POST',
    body: JSON.stringify(id ? { id } : {}),
  });
