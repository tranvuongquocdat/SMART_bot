import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Project = {
  id: number;
  name: string;
  description: string | null;
  items_count: number;
  created_at: string;
  updated_at: string;
};

export const projectsQuery = () =>
  queryOptions({
    queryKey: ['admin', 'projects'],
    queryFn: () => api<Project[]>('/api/v1/admin/projects'),
  });

export const createProject = (body: { name: string; description?: string }) =>
  api<Project>('/api/v1/admin/projects', { method: 'POST', body: JSON.stringify(body) });

export const deleteProject = (id: number) =>
  api<void>(`/api/v1/admin/projects/${id}`, { method: 'DELETE' });
