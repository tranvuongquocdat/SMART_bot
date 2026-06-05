import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type NoteTemplate = {
  id: number;
  name: string;
  description: string | null;
  is_system: boolean;
  owner_boss_id: number | null;
  sections_json: unknown[];
  created_at: string | null;
  updated_at: string | null;
};

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export const noteTemplatesQuery = queryOptions({
  queryKey: ['superadmin', 'note-templates'] as const,
  queryFn: () => api<NoteTemplate[]>('/api/v1/superadmin/note-templates'),
});

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export async function createNoteTemplate(body: {
  name: string;
  description?: string | null;
  is_system?: boolean;
  sections_json?: unknown[];
}) {
  return api<{ id: number }>('/api/v1/superadmin/note-templates', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function patchNoteTemplate(
  id: number,
  body: { name?: string; description?: string | null; sections_json?: unknown[] },
) {
  return api<{ id: number; ok: boolean }>(`/api/v1/superadmin/note-templates/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deleteNoteTemplate(id: number) {
  return api<void>(`/api/v1/superadmin/note-templates/${id}`, { method: 'DELETE' });
}
