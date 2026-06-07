import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import { staggerContainer, fadeUp } from '@/lib/motion';
import { cn } from '@/lib/utils';

/**
 * Standard outer wrapper for admin/superadmin pages.
 * Matches the dashboard's `px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1140px] mx-auto`
 * and applies the same fadeUp+stagger entrance.
 */
export function PageWrap({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      className={cn(
        'px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1140px] mx-auto space-y-5',
        className,
      )}
      variants={staggerContainer(0.08)}
      initial="hidden"
      animate="show"
    >
      {children}
    </motion.div>
  );
}

/**
 * Standard page header — title + subtitle + optional right-side actions.
 * Auto-wraps in a fadeUp motion variant so it animates with the page.
 */
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <motion.div variants={fadeUp} className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[26px] font-semibold tracking-[-0.02em] leading-tight">{title}</h1>
        {subtitle && (
          <p className="text-muted-foreground mt-1 text-[12.5px]">{subtitle}</p>
        )}
      </div>
      {actions && <div className="shrink-0 flex items-center gap-2">{actions}</div>}
    </motion.div>
  );
}

/**
 * Section wrapper — animated fadeUp, useful for content blocks under PageHeader.
 */
export function PageSection({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div variants={fadeUp} className={className}>
      {children}
    </motion.div>
  );
}
