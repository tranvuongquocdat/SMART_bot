import type { QueryClient } from '@tanstack/react-query';
import type { RouteObject } from 'react-router-dom';
import { requireRole } from '@/lib/rbac';
import AdminLayout from './layout';
import GroupDetail, { groupDetailLoader } from './features/groups/group-detail';

export function adminRoutes(qc: QueryClient): RouteObject {
  return {
    path: '/app/admin',
    element: <AdminLayout />,
    loader: requireRole('boss', qc),
    id: 'admin',
    handle: { breadcrumb: 'Admin' },
    children: [
      { index: true, lazy: async () => ({ Component: (await import('./features/dashboard/page')).default }) },
      { path: 'dashboard', lazy: async () => ({ Component: (await import('./features/dashboard/page')).default }), handle: { breadcrumb: 'Dashboard' } },
      { path: 'groups', lazy: async () => ({ Component: (await import('./features/groups/list-page')).default }), handle: { breadcrumb: 'Groups' } },
      {
        path: 'groups/:groupId',
        element: <GroupDetail />,
        loader: groupDetailLoader(qc),
        handle: { breadcrumb: 'Group' },
      },
    ],
  };
}
