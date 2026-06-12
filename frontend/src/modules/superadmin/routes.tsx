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
    handle: { breadcrumb: 'Super-admin' },
    children: [
      { index: true, lazy: async () => ({ Component: (await import('./features/models/page')).default }) },
      { path: 'models', lazy: async () => ({ Component: (await import('./features/models/page')).default }), handle: { breadcrumb: 'Models AI' } },
      { path: 'bot-accounts', lazy: async () => ({ Component: (await import('./features/bot-accounts/page')).default }), handle: { breadcrumb: 'Tài khoản bot' } },
      { path: 'bosses', lazy: async () => ({ Component: (await import('./features/bosses/page')).default }), handle: { breadcrumb: 'Boss' } },
      { path: 'proxies', lazy: async () => ({ Component: (await import('./features/proxies/page')).default }), handle: { breadcrumb: 'Proxy' } },
      {
        path: 'prompts',
        handle: { breadcrumb: 'Prompts' },
        children: [
          { index: true, lazy: async () => ({ Component: (await import('./features/prompts/list-page')).default }) },
          { path: ':id', lazy: async () => ({ Component: (await import('./features/prompts/detail-page')).default }), handle: { breadcrumb: 'Chi tiết prompt' } },
        ],
      },
      { path: 'note-templates', lazy: async () => ({ Component: (await import('./features/note-templates/page')).default }), handle: { breadcrumb: 'Note templates' } },
      { path: 'agent-triggers', lazy: async () => ({ Component: (await import('./features/agent-triggers/page')).default }), handle: { breadcrumb: 'Agent triggers' } },
      { path: 'audit', lazy: async () => ({ Component: (await import('./features/audit-log/page')).default }), handle: { breadcrumb: 'Audit log' } },
      { path: 'retrieval-pipelines', lazy: async () => ({ Component: (await import('./features/retrieval-pipelines/page')).default }), handle: { breadcrumb: 'Retrieval pipelines' } },
      { path: 'usage', lazy: async () => ({ Component: (await import('./features/usage/page')).default }), handle: { breadcrumb: 'Sử dụng' } },
      { path: 'subscriptions', lazy: async () => ({ Component: (await import('./features/subscriptions/page')).default }), handle: { breadcrumb: 'Yêu cầu đăng ký' } },
      { path: 'plans', lazy: async () => ({ Component: (await import('./features/plans/page')).default }), handle: { breadcrumb: 'Gói dịch vụ' } },
      { path: 'mcp-catalog', lazy: async () => ({ Component: (await import('./features/mcp-catalog/page')).default }), handle: { breadcrumb: 'MCP Catalog' } },
    ],
  };
}
