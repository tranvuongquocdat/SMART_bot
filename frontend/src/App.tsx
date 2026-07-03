import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { adminRoutes } from './modules/admin/routes';
import { superadminRoutes } from './modules/superadmin/routes';
import { requireAuth } from './lib/rbac';
import { I18nProvider } from './lib/i18n';
import { Toaster } from '@/components/ui/sonner';
import LoginPage from './routes/login-page';
import LegalPage from './routes/legal-page';

const qc = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
});

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  // Trang điều khoản public — không qua requireAuth.
  { path: '/app/legal/:kind', element: <LegalPage /> },
  { path: '/app', loader: requireAuth(qc), id: 'root' },
  adminRoutes(qc),
  superadminRoutes(qc),
]);

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <I18nProvider>
        <RouterProvider router={router} />
        <Toaster />
      </I18nProvider>
    </QueryClientProvider>
  );
}
