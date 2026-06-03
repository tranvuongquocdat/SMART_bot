import type { QueryClient } from '@tanstack/react-query';
import type { RouteObject } from 'react-router-dom';
import { requireRole } from '@/lib/rbac';
import SuperadminLayout from './layout';

export function superadminRoutes(qc: QueryClient): RouteObject {
  return {
    path: '/app/superadmin',
    element: <SuperadminLayout />,
    loader: requireRole('superadmin', qc),
    id: 'superadmin',
    handle: { breadcrumb: 'Super-admin' },
    children: [
      { index: true, lazy: async () => ({ Component: (await import('./features/models/page')).default }) },
      { path: 'models', lazy: async () => ({ Component: (await import('./features/models/page')).default }), handle: { breadcrumb: 'Models & Bots' } },
    ],
  };
}
