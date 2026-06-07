import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { adminRoutes } from './modules/admin/routes';
import { superadminRoutes } from './modules/superadmin/routes';
import { requireAuth } from './lib/rbac';
import { Toaster } from '@/components/ui/sonner';
import LoginPage from './routes/login-page';

const qc = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
});

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/app', loader: requireAuth(qc), id: 'root' },
  adminRoutes(qc),
  superadminRoutes(qc),
]);

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>
  );
}
