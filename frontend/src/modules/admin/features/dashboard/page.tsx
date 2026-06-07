import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
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

function greet(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Chào buổi sáng';
  if (h < 18) return 'Chào buổi chiều';
  return 'Chào buổi tối';
}

export default function DashboardPage() {
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
          <p className="text-[12.5px] font-medium text-foreground">Không tải được dashboard</p>
          <p className="text-[11px] text-muted-foreground mt-1">
            Có thể do mạng hoặc phiên đăng nhập. Thử lại?
          </p>
          <Button size="sm" className="mt-3" onClick={() => refetch()}>
            Thử lại
          </Button>
        </div>
      </div>
    );
  }

  return (
    <motion.div
      className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1140px] space-y-5"
      variants={staggerContainer(0.08)}
      initial="hidden"
      animate="show"
    >
      <motion.header variants={fadeUp}>
        <h1 className="text-[26px] font-semibold tracking-tight leading-tight">
          {greet()}, <span className="text-accent-gradient">boss.</span>
        </h1>
        <p className="text-muted-foreground mt-1 text-[12.5px]">Tổng quan workspace · 30 ngày qua</p>
      </motion.header>

      <motion.div className="grid grid-cols-2 md:grid-cols-4 gap-3" variants={staggerContainer(0.06)}>
        <StatCard label="Tin nhắn" value={data.stats_30d.messages} previous={data.stats_prev_30d.messages} />
        <StatCard label="Việc cần làm" value={data.stats_30d.tasks} previous={data.stats_prev_30d.tasks} />
        <StatCard label="Nhắc nhở" value={data.stats_30d.reminders} previous={data.stats_prev_30d.reminders} />
        <StatCard label="Quyết định" value={data.stats_30d.decisions} previous={data.stats_prev_30d.decisions} />
      </motion.div>

      <motion.div className="grid md:grid-cols-2 gap-3" variants={staggerContainer(0.08)}>
        <RecentGroups groups={data.recent_groups} />
        <TodayItems items={data.today_items} />
      </motion.div>

      <ActivityFeed items={data.recent_activity} />
    </motion.div>
  );
}
