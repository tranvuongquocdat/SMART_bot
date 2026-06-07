import { useQuery } from '@tanstack/react-query';
import { MessageSquare, CheckSquare, Bell, BarChart2, Users, ClipboardList } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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
  stats_30d: {
    messages: number;
    tasks: number;
    reminders: number;
    decisions: number;
  };
  recent_activity: Array<{
    kind: string;
    id: number;
    title: string;
    status: string;
    ts: string;
  }>;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function providerColor(provider: string): string {
  if (provider === 'zalo') return 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300';
  if (provider === 'telegram') return 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300';
  if (provider === 'web') return 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300';
  return 'bg-gray-100 text-gray-600';
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

type StatCardProps = {
  label: string;
  value: number;
  icon: React.ElementType;
  color: string;
};

function StatCard({ label, value, icon: Icon, color }: StatCardProps) {
  return (
    <div className="rounded-[12px] border bg-card px-5 py-4 flex items-center gap-4">
      <div className={`rounded-[8px] p-2.5 ${color}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <div className="text-2xl font-bold leading-tight">{value.toLocaleString()}</div>
        <div className="text-xs text-muted-foreground mt-0.5">{label}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section card wrapper
// ---------------------------------------------------------------------------

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-[12px] border bg-card">
      <div className="px-5 py-3.5 border-b">
        <h2 className="text-sm font-semibold">{title}</h2>
      </div>
      <div className="px-5 py-3">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin', 'dashboard'],
    queryFn: () => api<DashboardData>('/api/v1/admin/dashboard'),
    staleTime: 30_000,
  });

  const greeting = (() => {
    const h = new Date().getHours();
    if (h < 12) return 'Chào buổi sáng';
    if (h < 18) return 'Chào buổi chiều';
    return 'Chào buổi tối';
  })();

  if (isLoading) {
    return (
      <div className="px-10 py-8 max-md:px-4 max-md:py-6 space-y-6 max-w-[1140px]">
        <Skeleton className="h-8 w-64 rounded-[8px]" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-20 rounded-[12px]" />)}
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          <Skeleton className="h-[260px] rounded-[12px]" />
          <Skeleton className="h-[260px] rounded-[12px]" />
        </div>
        <Skeleton className="h-[200px] rounded-[12px]" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="px-10 py-8 max-md:px-4">
        <p className="text-destructive text-sm">Lỗi tải dashboard. Thử lại sau.</p>
      </div>
    );
  }

  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1140px] space-y-6">
      {/* Hero greeting */}
      <header>
        <h1 className="text-[26px] font-semibold tracking-tight">{greeting}, boss!</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Tổng quan workspace trong 30 ngày qua.
        </p>
      </header>

      {/* 4 stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Tin nhắn (30 ngày)"
          value={data.stats_30d.messages}
          icon={MessageSquare}
          color="bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300"
        />
        <StatCard
          label="Việc cần làm (30 ngày)"
          value={data.stats_30d.tasks}
          icon={CheckSquare}
          color="bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-300"
        />
        <StatCard
          label="Nhắc nhở (30 ngày)"
          value={data.stats_30d.reminders}
          icon={Bell}
          color="bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300"
        />
        <StatCard
          label="Quyết định (30 ngày)"
          value={data.stats_30d.decisions}
          icon={BarChart2}
          color="bg-purple-50 text-purple-600 dark:bg-purple-900/30 dark:text-purple-300"
        />
      </div>

      {/* 2-col: groups + today items */}
      <div className="grid md:grid-cols-2 gap-4">
        {/* Recent groups */}
        <SectionCard title="Nhóm gần đây">
          {data.recent_groups.length === 0 ? (
            <div className="flex flex-col items-center py-8 gap-2">
              <Users className="h-8 w-8 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">Chưa có nhóm nào</p>
            </div>
          ) : (
            <ul className="divide-y">
              {data.recent_groups.map(g => (
                <li key={g.id} className="py-2.5 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{g.name}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {relativeTime(g.updated_at)}
                    </div>
                  </div>
                  <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full shrink-0 ${providerColor(g.provider)}`}>
                    {g.provider}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        {/* Today's items */}
        <SectionCard title="Việc cần làm hôm nay">
          {data.today_items.length === 0 ? (
            <div className="flex flex-col items-center py-8 gap-2">
              <ClipboardList className="h-8 w-8 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">Không có việc cần làm</p>
            </div>
          ) : (
            <ul className="divide-y">
              {data.today_items.map(item => (
                <li key={item.id} className="py-2.5 flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm truncate">{item.text}</div>
                    <div className="text-xs text-muted-foreground mt-0.5 truncate">
                      {item.group_name}
                      {item.assignee_name && ` · ${item.assignee_name}`}
                    </div>
                  </div>
                  {item.due_at && (
                    <span className="text-[10px] text-muted-foreground shrink-0 mt-0.5">
                      {new Date(item.due_at).toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' })}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      {/* Recent activity feed */}
      <SectionCard title="Hoạt động gần đây">
        {data.recent_activity.length === 0 ? (
          <div className="flex flex-col items-center py-8 gap-2">
            <BarChart2 className="h-8 w-8 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">Chưa có hoạt động nào</p>
          </div>
        ) : (
          <ul className="divide-y">
            {data.recent_activity.map((a, i) => (
              <li key={`${a.kind}-${a.id}-${i}`} className="py-2.5 flex items-center gap-3">
                <Badge
                  variant={a.kind === 'action_item' ? 'default' : 'secondary'}
                  className="text-[10px] shrink-0"
                >
                  {a.kind === 'action_item' ? 'task' : a.kind}
                </Badge>
                <span className="text-sm truncate flex-1">{a.title}</span>
                <span className="text-xs text-muted-foreground shrink-0">{relativeTime(a.ts)}</span>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}
