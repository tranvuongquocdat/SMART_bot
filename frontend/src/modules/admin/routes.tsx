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
    handle: { breadcrumb: 'crumb.admin' },
    children: [
      { index: true, lazy: async () => ({ Component: (await import('./features/dashboard/page')).default }) },
      { path: 'dashboard', lazy: async () => ({ Component: (await import('./features/dashboard/page')).default }), handle: { breadcrumb: 'nav.admin.dashboard' } },
      { path: 'chat', lazy: async () => ({ Component: (await import('./features/chat/page')).default }), handle: { breadcrumb: 'nav.admin.chat' } },
      { path: 'ai', lazy: async () => ({ Component: (await import('./features/ai/page')).default }), handle: { breadcrumb: 'nav.admin.models' } },
      {
        path: 'groups',
        handle: { breadcrumb: 'nav.admin.groups' },
        children: [
          { index: true, lazy: async () => ({ Component: (await import('./features/groups/list-page')).default }) },
          {
            path: ':groupId',
            element: <GroupDetail />,
            loader: groupDetailLoader(qc),
            handle: { breadcrumb: 'crumb.groupDetail' },
          },
        ],
      },
      { path: 'reminders', lazy: async () => ({ Component: (await import('./features/reminders/page')).default }), handle: { breadcrumb: 'nav.admin.reminders' } },
      { path: 'projects', lazy: async () => ({ Component: (await import('./features/projects/page')).default }), handle: { breadcrumb: 'nav.admin.projects' } },
      { path: 'action-items', lazy: async () => ({ Component: (await import('./features/action-items/page')).default }), handle: { breadcrumb: 'nav.admin.actionItems' } },
      { path: 'performance', lazy: async () => ({ Component: (await import('./features/performance/page')).default }), handle: { breadcrumb: 'nav.admin.performance' } },
      { path: 'channels', lazy: async () => ({ Component: (await import('./features/channels/page')).default }), handle: { breadcrumb: 'nav.admin.channels' } },
      { path: 'usage', lazy: async () => ({ Component: (await import('./features/usage/page')).default }), handle: { breadcrumb: 'nav.admin.usage' } },
      { path: 'subscription', lazy: async () => ({ Component: (await import('./features/subscription/page')).default }), handle: { breadcrumb: 'nav.admin.subscription' } },
      { path: 'integrations', lazy: async () => ({ Component: (await import('./features/integrations/page')).default }), handle: { breadcrumb: 'nav.admin.integrations' } },
      { path: 'settings', lazy: async () => ({ Component: (await import('./features/settings/page')).default }), handle: { breadcrumb: 'nav.admin.settings' } },
    ],
  };
}
