import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Group = {
  id: number; name: string; channel: string;
  members_count: number; messages_30d: number; last_active_at: string | null;
};
export type GroupListItem = {
  id: number; name: string; channel: string; is_active: boolean;
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

export const toggleGroupActive = (id: number) =>
  api<{ id: number; is_active: boolean }>(
    `/api/v1/admin/groups/${id}/toggle-active`,
    { method: 'PATCH' },
  );

export const enableAllGroups = () =>
  api<{ enabled: number; active: number; total: number; limit: number | null }>(
    '/api/v1/admin/groups/enable-all',
    { method: 'POST', body: JSON.stringify({}) },
  );

export const disableAllGroups = () =>
  api<{ disabled: number; active: number }>(
    '/api/v1/admin/groups/disable-all',
    { method: 'POST', body: JSON.stringify({}) },
  );

// Group note — lõi của nhóm
export type GroupNote = {
  content: string;
  template_id: number | null;
  manually_edited_sections: string[];
  updated_at: string | null;
};
export type NoteVersion = {
  id: number;
  emitted_by: string;
  emitted_at: string;
  content_len: number;
};
export type NoteTemplate = { id: number; name: string; description: string | null };

export const noteQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'note'],
  queryFn: () => api<GroupNote>(`${base(id)}/note`),
});
export const noteVersionsQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'note-versions'],
  queryFn: () => api<NoteVersion[]>(`${base(id)}/note/versions`),
});
export const noteTemplatesQuery = () => queryOptions({
  queryKey: ['admin', 'note-templates'],
  queryFn: () => api<NoteTemplate[]>('/api/v1/admin/note-templates'),
});

export const patchNote = (id: string, content: string) =>
  api<{ ok: boolean }>(`${base(id)}/note`, {
    method: 'PATCH', body: JSON.stringify({ content }),
  });
export const refreshNote = (id: string) =>
  api<{ ok: boolean; message: string }>(`${base(id)}/note/refresh`, {
    method: 'POST', body: JSON.stringify({}),
  });
export const restoreNoteVersion = (id: string, versionId: number) =>
  api<{ ok: boolean }>(`${base(id)}/note/versions/${versionId}/restore`, {
    method: 'POST', body: JSON.stringify({}),
  });
export const setGroupTemplate = (id: string, templateId: number | null) =>
  api<{ ok: boolean }>(`${base(id)}/template`, {
    method: 'PATCH', body: JSON.stringify({ template_id: templateId }),
  });
