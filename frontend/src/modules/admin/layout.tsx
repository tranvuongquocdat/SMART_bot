import { Outlet, useLoaderData, useMatches } from 'react-router-dom';
import { AppShell } from '@/components/app-shell';
import type { Me } from '@/lib/auth';
import { adminNav } from './nav';

export default function AdminLayout() {
  const me = useLoaderData() as Me;
  const matches = useMatches();
  const crumbs = matches
    .filter(m => m.handle && (m.handle as any).breadcrumb)
    .map(m => (m.handle as any).breadcrumb);
  return (
    <AppShell
      nav={adminNav}
      me={me}
      breadcrumb={
        crumbs.length > 0 ? (
          crumbs.map((c, i) => (
            <span key={i}>
              {i > 0 && <span className="mx-2 text-[hsl(var(--dim))]">/</span>}
              {i === crumbs.length - 1 ? <b className="text-foreground font-medium">{c}</b> : c}
            </span>
          ))
        ) : (
          'Admin'
        )
      }
    >
      <Outlet />
    </AppShell>
  );
}
