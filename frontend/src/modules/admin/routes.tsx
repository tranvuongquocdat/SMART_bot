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
      { path: 'dashboard', lazy: async () => ({ Component: (await import('./features/dashboard/page')).default }), handle: { breadcrumb: 'Dashboard' } },
      { path: 'groups', lazy: async () => ({ Component: (await import('./features/groups/list-page')).default }), handle: { breadcrumb: 'Groups' } },
      {
        path: 'groups/:groupId',
        element: <GroupDetail />,
        loader: groupDetailLoader(qc),
        handle: { breadcrumb: 'Group' },
      },
      { path: 'reminders', lazy: async () => ({ Component: (await import('./features/reminders/page')).default }), handle: { breadcrumb: 'Reminders' } },
      { path: 'projects', lazy: async () => ({ Component: (await import('./features/projects/page')).default }), handle: { breadcrumb: 'Projects' } },
      { path: 'action-items', lazy: async () => ({ Component: (await import('./features/action-items/page')).default }), handle: { breadcrumb: 'Action items' } },
      { path: 'channels', lazy: async () => ({ Component: (await import('./features/channels/page')).default }), handle: { breadcrumb: 'Channels' } },
      { path: 'usage', lazy: async () => ({ Component: (await import('./features/usage/page')).default }), handle: { breadcrumb: 'Usage' } },
      { path: 'subscription', lazy: async () => ({ Component: (await import('./features/subscription/page')).default }), handle: { breadcrumb: 'Subscription' } },
      { path: 'settings', lazy: async () => ({ Component: (await import('./features/settings/page')).default }), handle: { breadcrumb: 'Cai dat' } },
    ],
  };
}
