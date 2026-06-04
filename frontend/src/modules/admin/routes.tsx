import type { QueryClient } from '@tanstack/react-query';
import type { RouteObject } from 'react-router-dom';
import { requireRole } from '@/lib/rbac';
import AdminLayout from './layout';
import GroupDetail, { groupDetailLoader } from './features/groups/group-detail';
import ComingSoon from '@/components/coming-soon';
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
      { path: 'dashboard', lazy: async () => ({ Component: (await import('./features/dashboard/page')).default }), handle: { breadcrumb: 'Dashboard' } },
      { path: 'groups', lazy: async () => ({ Component: (await import('./features/groups/list-page')).default }), handle: { breadcrumb: 'Groups' } },
      {
        path: 'groups/:groupId',
        element: <GroupDetail />,
        loader: groupDetailLoader(qc),
        handle: { breadcrumb: 'Group' },
      },
      { path: 'reminders', lazy: async () => ({ Component: (await import('./features/reminders/page')).default }), handle: { breadcrumb: 'Reminders' } },
      { path: 'projects', element: <ComingSoon feature="Projects" />, handle: { breadcrumb: 'Projects' } },
      { path: 'channels', element: <ComingSoon feature="Channels" />, handle: { breadcrumb: 'Channels' } },
      { path: 'settings', lazy: async () => ({ Component: (await import('./features/settings/page')).default }), handle: { breadcrumb: 'Cai dat' } },
    ],
  };
}
