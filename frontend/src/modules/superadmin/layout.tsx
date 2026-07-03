import { Link, Outlet, useLoaderData, useLocation, useMatches } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { AppShell } from '@/components/app-shell';
import { api } from '@/lib/api';
import { pageTransition } from '@/lib/motion';
import { useT } from '@/lib/i18n';
import type { Me } from '@/lib/auth';
import { superadminNav } from './nav';
import { LegalGate } from '@/components/legal-gate';

export default function SuperadminLayout() {
  const t = useT();
  const me = useLoaderData() as Me;
  // Badge việc chờ: thanh toán manual → superadmin phải thấy request pending ngay.
  const { data: pending } = useQuery({
    queryKey: ['superadmin', 'subscription-pending-count'],
    queryFn: () =>
      api<{ count: number }>('/api/v1/superadmin/subscription-requests/pending-count'),
    refetchInterval: 60_000,
  });
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
      badges={{ '/app/superadmin/subscriptions': pending?.count }}
      breadcrumb={
        crumbs.length > 0 ? (
          crumbs.map((c, i) => {
            const isLast = i === crumbs.length - 1;
            return (
              <span key={i}>
                {i > 0 && <span className="mx-2 text-[hsl(var(--dim))]">/</span>}
                {isLast ? (
                  <b className="text-foreground font-medium">{t(c.label)}</b>
                ) : (
                  <Link to={c.pathname} className="hover:text-foreground transition-colors">
                    {t(c.label)}
                  </Link>
                )}
              </span>
            );
          })
        ) : (
          t('crumb.superadmin')
        )
      }
    >
      <LegalGate />
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
