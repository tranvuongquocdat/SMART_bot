import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Channel = {
  provider: string;
  display_name: string | null;
  status: string;
  assign_status: string;
  status_dot: 'ok' | 'warn' | 'err' | 'idle';
  assignment_kind: string | null;
  ownership: string | null;
  connected_at: string | null;
};

export type ConnectResult = {
  provider: string;
  status: string;
  display_name: string | null;
};

export const channelsQuery = () =>
  queryOptions({
    queryKey: ['admin', 'channels'],
    queryFn: () => api<Channel[]>('/api/v1/admin/channels'),
  });

export const connectChannel = (provider: string) =>
  api<ConnectResult>(`/api/v1/admin/channels/${encodeURIComponent(provider)}/connect`, {
    method: 'POST',
    body: JSON.stringify({}),
  });

export const disconnectChannel = (provider: string) =>
  api<{ deleted: boolean; provider: string }>(
    `/api/v1/admin/channels/${encodeURIComponent(provider)}`,
    { method: 'DELETE' },
  );

export type ZaloQrStatus = {
  status: 'starting' | 'qr' | 'scanned' | 'success' | 'error';
  qr_image_b64: string | null;
  display_name: string | null;
  error: string | null;
  bot_account_id: number | null;
  expires_in_s: number;
};

export const startZaloQrLogin = () =>
  api<{ login_id: string; status: string }>('/api/v1/admin/channels/zalo/qr-login', {
    method: 'POST',
    body: JSON.stringify({}),
  });

export const zaloQrLoginStatus = (loginId: string) =>
  api<ZaloQrStatus>(`/api/v1/admin/channels/zalo/qr-login/${loginId}`);

export type LinkToken = { token: string; bot_name: string };

export const mintLinkToken = (provider: string) =>
  api<LinkToken>(
    `/api/v1/admin/channels/${encodeURIComponent(provider)}/link-token`,
    { method: 'POST', body: JSON.stringify({}) }
  );
