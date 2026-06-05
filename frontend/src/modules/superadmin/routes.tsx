import type { QueryClient } from '@tanstack/react-query';
import type { RouteObject } from 'react-router-dom';
import { requireRole } from '@/lib/rbac';
import SuperadminLayout from './layout';
import ComingSoon from '@/components/coming-soon';
import RootError from '@/components/root-error';

export function superadminRoutes(qc: QueryClient): RouteObject {
  return {
    path: '/app/superadmin',
    element: <SuperadminLayout />,
    loader: requireRole('superadmin', qc),
    errorElement: <RootError />,
    id: 'superadmin',
    handle: { breadcrumb: 'Super-admin' },
    children: [
      { index: true, lazy: async () => ({ Component: (await import('./features/models/page')).default }) },
      { path: 'models', lazy: async () => ({ Component: (await import('./features/models/page')).default }), handle: { breadcrumb: 'Models' } },
      { path: 'bot-accounts', lazy: async () => ({ Component: (await import('./features/bot-accounts/page')).default }), handle: { breadcrumb: 'Bot accounts' } },
      { path: 'bosses', lazy: async () => ({ Component: (await import('./features/bosses/page')).default }), handle: { breadcrumb: 'Bosses' } },
      { path: 'prompts', lazy: async () => ({ Component: (await import('./features/prompts/list-page')).default }), handle: { breadcrumb: 'Prompts' } },
      { path: 'prompts/:id', lazy: async () => ({ Component: (await import('./features/prompts/detail-page')).default }), handle: { breadcrumb: 'Prompt detail' } },
      { path: 'note-templates', lazy: async () => ({ Component: (await import('./features/note-templates/page')).default }), handle: { breadcrumb: 'Note templates' } },
      { path: 'agent-triggers', lazy: async () => ({ Component: (await import('./features/agent-triggers/page')).default }), handle: { breadcrumb: 'Agent triggers' } },
      { path: 'audit', element: <ComingSoon feature="Audit log" />, handle: { breadcrumb: 'Audit log' } },
      { path: 'usage', element: <ComingSoon feature="Usage" />, handle: { breadcrumb: 'Usage' } },
    ],
  };
}
