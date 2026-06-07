import { api } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AuditLogItem = {
  id: number;
  actor_user_id: number;
  actor_email: string | null;
  actor_name: string | null;
  action: string;
  target_kind: string | null;
  target_id: string | null;
  reason: string | null;
  payload_json: unknown | null;
  created_at: string;
};

export type AuditLogPage = {
  items: AuditLogItem[];
  next_cursor: string | null;
};

// ---------------------------------------------------------------------------
// Fetch
// ---------------------------------------------------------------------------

export async function fetchAuditLog(params: {
  cursor?: string | null;
  actor?: string;
  action?: string;
  limit?: number;
}): Promise<AuditLogPage> {
  const sp = new URLSearchParams();
  if (params.cursor) sp.set('cursor', params.cursor);
  if (params.actor) sp.set('actor', params.actor);
  if (params.action) sp.set('action', params.action);
  if (params.limit) sp.set('limit', String(params.limit));
  const qs = sp.toString();
  return api<AuditLogPage>(`/api/v1/superadmin/audit-log${qs ? `?${qs}` : ''}`);
}
