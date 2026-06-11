import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type ChatMessage = {
  kind: 'in' | 'out';
  id: string | number;
  sender_name: string | null;
  text: string;
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

export const chatMessagesQuery = () =>
  queryOptions({
    queryKey: ['admin', 'chat', 'messages'],
    queryFn: () => api<ChatMessage[]>('/api/v1/admin/chat/messages'),
    staleTime: 0,
  });

export const sendChatMessage = (text: string) =>
  api<{ ok: boolean }>('/api/v1/admin/chat/send', {
    method: 'POST',
    body: JSON.stringify({ text }),
  });

export const CHAT_STREAM_URL = '/api/v1/admin/chat/stream';
