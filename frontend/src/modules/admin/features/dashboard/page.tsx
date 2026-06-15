import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { staggerContainer, fadeUp } from '@/lib/motion';
import { StatCard } from './components/stat-card';
import { RecentGroups } from './components/recent-groups';
import { TodayItems } from './components/today-items';
import { ActivityFeed } from './components/activity-feed';
import { DashboardSkeleton } from './components/dashboard-skeleton';

type DashboardData = {
  recent_groups: Array<{
    id: number;
    name: string;
    provider: string;
    msg_count_7d: number;
    updated_at: string;
  }>;
  today_items: Array<{
    id: number;
    text: string;
    due_at: string | null;
    status: string;
    assignee_name: string | null;
    group_name: string;
  }>;
  stats_30d: { messages: number; tasks: number; reminders: number; decisions: number };
  stats_prev_30d: { messages: number; tasks: number; reminders: number; decisions: number };
  recent_activity: Array<{ kind: string; id: number; title: string; status: string; ts: string }>;
};

export default function DashboardPage() {
  const t = useT();
  const greetKey =
    new Date().getHours() < 12
      ? 'dash.greet.morning'
      : new Date().getHours() < 18
        ? 'dash.greet.afternoon'
        : 'dash.greet.evening';
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['admin', 'dashboard'],
    queryFn: () => api<DashboardData>('/api/v1/admin/dashboard'),
    staleTime: 30_000,
  });

  if (isLoading) return <DashboardSkeleton />;

  if (isError || !data) {
    return (
      <div className="px-10 py-8 max-md:px-4">
        <div className="rounded-[12px] border border-border bg-card px-5 py-6 max-w-md">
          <p className="text-[12.5px] font-medium text-foreground">{t('dash.loadError')}</p>
          <p className="text-[11px] text-muted-foreground mt-1">{t('dash.loadErrorHint')}</p>
          <Button size="sm" className="mt-3" onClick={() => refetch()}>
            {t('common.retry')}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <motion.div
      className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1280px] mx-auto space-y-6"
      variants={staggerContainer(0.08)}
      initial="hidden"
      animate="show"
    >
      <motion.header variants={fadeUp}>
        <h1 className="text-[26px] font-semibold tracking-tight leading-tight">
          {t(greetKey)}, <span className="text-accent-gradient">boss.</span>
        </h1>
        <p className="text-muted-foreground mt-1 text-[12.5px]">{t('dash.subtitle')}</p>
      </motion.header>

      <motion.div className="grid grid-cols-2 md:grid-cols-4 gap-4" variants={staggerContainer(0.06)}>
        <StatCard label={t('dash.stat.messages')} value={data.stats_30d.messages} previous={data.stats_prev_30d.messages} />
        <StatCard label={t('dash.stat.tasks')} value={data.stats_30d.tasks} previous={data.stats_prev_30d.tasks} />
        <StatCard label={t('dash.stat.reminders')} value={data.stats_30d.reminders} previous={data.stats_prev_30d.reminders} />
        <StatCard label={t('dash.stat.decisions')} value={data.stats_30d.decisions} previous={data.stats_prev_30d.decisions} />
      </motion.div>

      <motion.div className="grid md:grid-cols-2 gap-3" variants={staggerContainer(0.08)}>
        <RecentGroups groups={data.recent_groups} />
        <TodayItems items={data.today_items} />
      </motion.div>

      <ActivityFeed items={data.recent_activity} />
    </motion.div>
  );
}
