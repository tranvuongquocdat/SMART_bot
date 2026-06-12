import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Announcement = {
  id: number;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  created_at: string;
};

export const announcementsQuery = queryOptions({
  queryKey: ['superadmin', 'announcements'] as const,
  queryFn: () => api<Announcement[]>('/api/v1/superadmin/announcements'),
});

export const createAnnouncement = (body: {
  title: string;
  body?: string;
  link?: string;
  kind?: string;
}) =>
  api<{ id: number }>('/api/v1/superadmin/announcements', {
    method: 'POST',
    body: JSON.stringify(body),
  });
