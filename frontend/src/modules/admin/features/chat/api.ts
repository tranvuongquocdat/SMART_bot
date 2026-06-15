import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type ChatMessage = {
  kind: 'in' | 'out';
  id: string | number;
  sender_name: string | null;
  text: string | null;
  media_kind: string | null;
  media_url: string | null;
  ts: string;
};

export type ChatStreamEvent = {
  kind: string;
  chat_id: string;
  msg_id: string;
  sender_kind: 'user' | 'bot';
  sender_id: string | null;
  sender_name: string | null;
  text: string;
  ts: string;
};

export type Conversation = {
  id: string;
  name: string;
  created_at: string;
  last_message_at: string | null;
  last_message: string | null;
};

export type Attachment = { url: string; name: string; kind: 'image' | 'file' };

export const conversationsQuery = () =>
  queryOptions({
    queryKey: ['admin', 'chat', 'conversations'],
    queryFn: () => api<Conversation[]>('/api/v1/admin/chat/conversations'),
  });

export const chatMessagesQuery = (conversationId: string | null) =>
  queryOptions({
    queryKey: ['admin', 'chat', 'messages', conversationId ?? 'default'],
    queryFn: () =>
      api<ChatMessage[]>(
        `/api/v1/admin/chat/messages${conversationId ? `?conversation_id=${conversationId}` : ''}`
      ),
    staleTime: 0,
  });

export const createConversation = (name?: string) =>
  api<{ id: string; name: string }>('/api/v1/admin/chat/conversations', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });

export const renameConversation = (id: string, name: string) =>
  api<{ id: string; name: string }>(`/api/v1/admin/chat/conversations/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  });

export const deleteConversation = (id: string) =>
  api(`/api/v1/admin/chat/conversations/${id}`, { method: 'DELETE' });

export const sendChatMessage = (body: {
  text: string;
  conversation_id?: string | null;
  attachment?: Attachment | null;
}) =>
  api<{ ok: boolean }>('/api/v1/admin/chat/send', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const cancelChat = (conversationId: string | null) =>
  api<{ cancelled: number }>('/api/v1/admin/chat/cancel', {
    method: 'POST',
    body: JSON.stringify({ conversation_id: conversationId }),
  });

export async function uploadChatFile(file: File): Promise<Attachment> {
  const m = document.cookie.match(/(?:^|;\s*)smart_csrf=([^;]+)/);
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/v1/admin/chat/upload', {
    method: 'POST',
    headers: { 'X-CSRF-Token': m ? decodeURIComponent(m[1]) : '' },
    body: fd,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? 'Tải tệp thất bại');
  }
  return res.json();
}

export const chatStreamUrl = (conversationId: string | null) =>
  `/api/v1/admin/chat/stream${conversationId ? `?conversation_id=${conversationId}` : ''}`;
