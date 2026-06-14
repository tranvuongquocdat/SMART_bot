import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

// Core/built-in tools: luôn bật cho mọi boss, không tắt được, không cap.
// Hiển thị read-only (list thu gọn dưới phần Integrations). Không còn toggle.
export type Tool = {
  name: string;
  description: string;
  core: boolean;
  active: boolean;
  can_disable: boolean;
};

export const toolsQuery = () =>
  queryOptions({
    queryKey: ['admin', 'tools'],
    queryFn: () => api<Tool[]>('/api/v1/admin/tools'),
  });
