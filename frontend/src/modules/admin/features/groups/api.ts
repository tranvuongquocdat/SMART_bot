import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Group = {
  id: number; name: string; channel: string;
  members_count: number; messages_30d: number; last_active_at: string | null;
};
export type GroupListItem = {
  id: number; name: string; channel: string;
  members_count: number; updated_at: string | null;
};
export type Summary = { body: string | null; updated_at: string | null };
export type Item = {
  id: number; type: 'task' | 'reminder' | 'decision';
  text: string; assignee: string | null; due_at: string | null; created_at: string;
};
export type TimelineMsg = {
  id: number; author_name: string;
  author_kind: 'boss' | 'member' | 'bot';
  text: string; created_at: string; extracted?: string;
};
export type Stats = { messages: number; tasks: number; reminders: number; decisions: number };
export type Member = { id: number; name: string; role: string; last_seen_at: string | null };
export type FileItem = { id: number; kind: 'doc' | 'link' | 'image'; name: string; url: string; created_at: string };
export type PersonResult = { id: number; display_name: string; external_id: string | null };

const base = (id: string) => `/api/v1/admin/groups/${id}`;

export const groupQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id], queryFn: () => api<Group>(base(id)),
});
export const summaryQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'summary'],
  queryFn: () => api<Summary>(`${base(id)}/summary?date=today`),
});
export const itemsQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'items'],
  queryFn: () => api<Item[]>(`${base(id)}/items?date=today`),
});
export const timelineQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'timeline'],
  queryFn: () => api<{ messages: TimelineMsg[]; next_cursor: string | null }>(`${base(id)}/timeline?limit=20`),
});
export const statsQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'stats'],
  queryFn: () => api<Stats>(`${base(id)}/stats?range=7d`),
});
export const membersQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'members'],
  queryFn: () => api<Member[]>(`${base(id)}/members`),
});
export const filesQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'files'],
  queryFn: () => api<FileItem[]>(`${base(id)}/files?limit=10`),
});

// SP2-4: groups list
export const groupsListQuery = () => queryOptions({
  queryKey: ['admin', 'groups'],
  queryFn: () => api<GroupListItem[]>('/api/v1/admin/groups'),
});

export const createGroup = (payload: { name: string; channel: string }) =>
  api<GroupListItem>('/api/v1/admin/groups', { method: 'POST', body: JSON.stringify(payload) });

export const deleteGroup = (id: number) =>
  api<void>(`/api/v1/admin/groups/${id}`, { method: 'DELETE' });

export const addMember = (groupId: string, payload: { display_name: string; external_id?: string; role?: string }) =>
  api<{ id: number; display_name: string; role: string | null; joined_at: string | null }>(
    `/api/v1/admin/groups/${groupId}/members`,
    { method: 'POST', body: JSON.stringify(payload) },
  );

export const removeMember = (groupId: string, memberId: number) =>
  api<void>(`/api/v1/admin/groups/${groupId}/members/${memberId}`, { method: 'DELETE' });

export const peopleSearchQuery = (q: string) => queryOptions({
  queryKey: ['admin', 'people', q],
  queryFn: () => api<PersonResult[]>(`/api/v1/admin/people?q=${encodeURIComponent(q)}`),
  enabled: q.length >= 1,
});
