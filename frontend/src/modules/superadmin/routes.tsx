import type { QueryClient } from '@tanstack/react-query';
import type { RouteObject } from 'react-router-dom';
import { requireRole } from '@/lib/rbac';
import SuperadminLayout from './layout';
import RootError from '@/components/root-error';

export function superadminRoutes(qc: QueryClient): RouteObject {
  return {
    path: '/app/superadmin',
    element: <SuperadminLayout />,
    loader: requireRole('superadmin', qc),
    errorElement: <RootError />,
    id: 'superadmin',
    handle: { breadcrumb: 'crumb.superadmin' },
    children: [
      { index: true, lazy: async () => ({ Component: (await import('./features/models/page')).default }) },
      { path: 'models', lazy: async () => ({ Component: (await import('./features/models/page')).default }), handle: { breadcrumb: 'nav.sa.models' } },
      { path: 'bot-accounts', lazy: async () => ({ Component: (await import('./features/bot-accounts/page')).default }), handle: { breadcrumb: 'nav.sa.botAccounts' } },
      { path: 'bosses', lazy: async () => ({ Component: (await import('./features/bosses/page')).default }), handle: { breadcrumb: 'nav.sa.bosses' } },
      { path: 'proxies', lazy: async () => ({ Component: (await import('./features/proxies/page')).default }), handle: { breadcrumb: 'nav.sa.proxies' } },
      {
        path: 'prompts',
        handle: { breadcrumb: 'nav.sa.prompts' },
        children: [
          { index: true, lazy: async () => ({ Component: (await import('./features/prompts/list-page')).default }) },
          { path: ':id', lazy: async () => ({ Component: (await import('./features/prompts/detail-page')).default }), handle: { breadcrumb: 'crumb.promptDetail' } },
        ],
      },
      { path: 'note-templates', lazy: async () => ({ Component: (await import('./features/note-templates/page')).default }), handle: { breadcrumb: 'nav.sa.noteTemplates' } },
      { path: 'agent-triggers', lazy: async () => ({ Component: (await import('./features/agent-triggers/page')).default }), handle: { breadcrumb: 'nav.sa.agentTriggers' } },
      { path: 'legal', lazy: async () => ({ Component: (await import('./features/legal/page')).default }), handle: { breadcrumb: 'nav.sa.legal' } },
      { path: 'announcements', lazy: async () => ({ Component: (await import('./features/announcements/page')).default }), handle: { breadcrumb: 'nav.sa.announcements' } },
      { path: 'audit', lazy: async () => ({ Component: (await import('./features/audit-log/page')).default }), handle: { breadcrumb: 'nav.sa.audit' } },
      { path: 'retrieval-pipelines', lazy: async () => ({ Component: (await import('./features/retrieval-pipelines/page')).default }), handle: { breadcrumb: 'nav.sa.retrieval' } },
      { path: 'usage', lazy: async () => ({ Component: (await import('./features/usage/page')).default }), handle: { breadcrumb: 'nav.sa.usage' } },
      { path: 'subscriptions', lazy: async () => ({ Component: (await import('./features/subscriptions/page')).default }), handle: { breadcrumb: 'nav.sa.subscriptions' } },
      { path: 'plans', lazy: async () => ({ Component: (await import('./features/plans/page')).default }), handle: { breadcrumb: 'nav.sa.plans' } },
      { path: 'mcp-catalog', lazy: async () => ({ Component: (await import('./features/mcp-catalog/page')).default }), handle: { breadcrumb: 'nav.sa.mcpCatalog' } },
      { path: 'integrations', lazy: async () => ({ Component: (await import('./features/integrations/page')).default }), handle: { breadcrumb: 'nav.sa.integrations' } },
    ],
  };
}
