import { Link, Outlet, useLoaderData, useLocation, useMatches } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { AppShell } from '@/components/app-shell';
import { pageTransition } from '@/lib/motion';
import type { Me } from '@/lib/auth';
import { superadminNav } from './nav';

export default function SuperadminLayout() {
  const me = useLoaderData() as Me;
  const matches = useMatches();
  const location = useLocation();
  const crumbs = matches
    .filter((m) => m.handle && (m.handle as any).breadcrumb)
    .map((m) => ({
      label: (m.handle as any).breadcrumb as string,
      pathname: m.pathname,
    }));
  return (
    <AppShell
      nav={superadminNav}
      me={me}
      breadcrumb={
        crumbs.length > 0 ? (
          crumbs.map((c, i) => {
            const isLast = i === crumbs.length - 1;
            return (
              <span key={i}>
                {i > 0 && <span className="mx-2 text-[hsl(var(--dim))]">/</span>}
                {isLast ? (
                  <b className="text-foreground font-medium">{c.label}</b>
                ) : (
                  <Link to={c.pathname} className="hover:text-foreground transition-colors">
                    {c.label}
                  </Link>
                )}
              </span>
            );
          })
        ) : (
          'Super-admin'
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
