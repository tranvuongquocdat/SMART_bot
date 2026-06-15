import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type CatalogItem = {
  id: number;
  name: string;
  description: string | null;
  icon_url: string | null;
};
export type McpServer = {
  id: number;
  name: string;
  url: string;
  enabled: boolean;
  created_at: string;
  catalog_id: number | null;
};
export type PluginInfo = {
  plugin_id: string;
  name: string;
  description: string | null;
  enabled: boolean;
};
export type IntegrationsData = {
  mcp_slots: number | null;
  mcp_used: number;
  catalog: CatalogItem[];
  servers: McpServer[];
  plugins: PluginInfo[];
};

export const integrationsQuery = () =>
  queryOptions({
    queryKey: ['admin', 'integrations'],
    queryFn: () => api<IntegrationsData>('/api/v1/admin/integrations'),
  });

export const addMcpServer = (catalogId: number) =>
  api<{ id: number }>('/api/v1/admin/mcp-servers', {
    method: 'POST',
    body: JSON.stringify({ catalog_id: catalogId }),
  });

export const toggleMcpServer = (id: number) =>
  api<{ id: number; enabled: boolean }>(`/api/v1/admin/mcp-servers/${id}/toggle`, {
    method: 'PATCH',
  });

export const deleteMcpServer = (id: number) =>
  api(`/api/v1/admin/mcp-servers/${id}`, { method: 'DELETE' });

export const togglePlugin = (pluginId: string) =>
  api<{ plugin_id: string; enabled: boolean }>(
    `/api/v1/admin/integrations/plugins/${pluginId}/toggle`,
    { method: 'PATCH' },
  );
