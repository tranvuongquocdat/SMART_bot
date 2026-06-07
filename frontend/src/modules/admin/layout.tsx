import { Outlet, useLoaderData, useLocation, useMatches } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { AppShell } from '@/components/app-shell';
import { pageTransition } from '@/lib/motion';
import type { Me } from '@/lib/auth';
import { adminNav } from './nav';

export default function AdminLayout() {
  const me = useLoaderData() as Me;
  const matches = useMatches();
  const location = useLocation();
  const crumbs = matches
    .filter((m) => m.handle && (m.handle as any).breadcrumb)
    .map((m) => (m.handle as any).breadcrumb);
  return (
    <AppShell
      nav={adminNav}
      me={me}
      breadcrumb={
        crumbs.length > 0 ? (
          crumbs.map((c, i) => (
            <span key={i}>
              {i > 0 && <span className="mx-2 text-[hsl(var(--dim))]">/</span>}
              {i === crumbs.length - 1 ? (
                <b className="text-foreground font-medium">{c}</b>
              ) : (
                c
              )}
            </span>
          ))
        ) : (
          'Admin'
        )
      }
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={location.pathname}
          initial={pageTransition.initial}
          animate={pageTransition.animate}
          exit={pageTransition.exit}
        >
          <Outlet />
        </motion.div>
      </AnimatePresence>
    </AppShell>
  );
}
