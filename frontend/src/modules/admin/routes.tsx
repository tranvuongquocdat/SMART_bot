import type { QueryClient } from '@tanstack/react-query';
import type { RouteObject } from 'react-router-dom';
import { requireRole } from '@/lib/rbac';
import AdminLayout from './layout';
import GroupDetail, { groupDetailLoader } from './features/groups/group-detail';
import RootError from '@/components/root-error';

export function adminRoutes(qc: QueryClient): RouteObject {
  return {
    path: '/app/admin',
    element: <AdminLayout />,
    loader: requireRole('boss', qc),
    errorElement: <RootError />,
    id: 'admin',
    handle: { breadcrumb: 'Admin' },
    children: [
      { index: true, lazy: async () => ({ Component: (await import('./features/dashboard/page')).default }) },
      { path: 'dashboard', lazy: async () => ({ Component: (await import('./features/dashboard/page')).default }), handle: { breadcrumb: 'Tổng quan' } },
      { path: 'chat', lazy: async () => ({ Component: (await import('./features/chat/page')).default }), handle: { breadcrumb: 'Trợ lý' } },
      {
        path: 'groups',
        handle: { breadcrumb: 'Nhóm' },
        children: [
          { index: true, lazy: async () => ({ Component: (await import('./features/groups/list-page')).default }) },
          {
            path: ':groupId',
            element: <GroupDetail />,
            loader: groupDetailLoader(qc),
            handle: { breadcrumb: 'Chi tiết nhóm' },
          },
        ],
      },
      { path: 'reminders', lazy: async () => ({ Component: (await import('./features/reminders/page')).default }), handle: { breadcrumb: 'Nhắc nhở' } },
      { path: 'projects', lazy: async () => ({ Component: (await import('./features/projects/page')).default }), handle: { breadcrumb: 'Dự án' } },
      { path: 'action-items', lazy: async () => ({ Component: (await import('./features/action-items/page')).default }), handle: { breadcrumb: 'Việc cần làm' } },
      { path: 'channels', lazy: async () => ({ Component: (await import('./features/channels/page')).default }), handle: { breadcrumb: 'Kênh kết nối' } },
      { path: 'usage', lazy: async () => ({ Component: (await import('./features/usage/page')).default }), handle: { breadcrumb: 'Sử dụng' } },
      { path: 'subscription', lazy: async () => ({ Component: (await import('./features/subscription/page')).default }), handle: { breadcrumb: 'Gói cước' } },
      { path: 'tools', lazy: async () => ({ Component: (await import('./features/tools/page')).default }), handle: { breadcrumb: 'Tools' } },
      { path: 'integrations', lazy: async () => ({ Component: (await import('./features/integrations/page')).default }), handle: { breadcrumb: 'Tích hợp' } },
      { path: 'settings', lazy: async () => ({ Component: (await import('./features/settings/page')).default }), handle: { breadcrumb: 'Cài đặt' } },
    ],
  };
}
