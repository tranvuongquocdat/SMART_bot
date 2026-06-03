import { useQuery } from '@tanstack/react-query';
import { Plus, Zap, RefreshCw, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { SlotCard } from './slot-card';
import { BotAccountsTable } from './bot-accounts-table';
import { slotsQuery, botAccountsQuery } from './api';

const SLOT_ICONS = { smart: RefreshCw, fast: Zap, vision: Eye } as const;

export default function ModelsPage() {
  const slots = useQuery(slotsQuery);
  const bots = useQuery(botAccountsQuery);

  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1140px]">
      <header className="mb-8">
        <h1 className="text-[24px] font-semibold tracking-tight">Models &amp; Bots</h1>
        <p className="text-muted-foreground mt-1.5">
          Quản lý các model mặc định và bot account đang vận hành toàn hệ thống.
        </p>
      </header>

      <Tabs defaultValue="default" className="mb-6">
        <TabsList>
          <TabsTrigger value="default">Default models</TabsTrigger>
          <TabsTrigger value="bots">Bot accounts</TabsTrigger>
          <TabsTrigger value="providers">Providers &amp; keys</TabsTrigger>
        </TabsList>
      </Tabs>

      <section className="mb-11">
        <div className="flex items-end justify-between mb-3.5 gap-3 flex-wrap">
          <div>
            <h2 className="text-[14.5px] font-semibold tracking-tight">Model slots</h2>
            <p className="text-[12.5px] text-muted-foreground mt-0.5">Boss có thể override; đây là giá trị mặc định.</p>
          </div>
          <Button variant="ghost" size="sm">Reset to factory</Button>
        </div>
        {slots.isLoading ? (
          <div className="grid grid-cols-3 gap-3 max-md:grid-cols-1">
            {[0, 1, 2].map(i => <Skeleton key={i} className="h-[180px] rounded-[10px]" />)}
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-3 max-md:grid-cols-1">
            {slots.data?.map(s => (
              <SlotCard key={s.slot} slot={s} icon={SLOT_ICONS[s.slot]} />
            ))}
          </div>
        )}
      </section>

      <section className="mb-11">
        <div className="flex items-end justify-between mb-3.5 gap-3 flex-wrap">
          <div>
            <h2 className="text-[14.5px] font-semibold tracking-tight">Bot accounts</h2>
            <p className="text-[12.5px] text-muted-foreground mt-0.5">
              Tài khoản Zalo cá nhân và Telegram bot đang chạy.
            </p>
          </div>
          <Button>
            <Plus className="h-3.5 w-3.5" />
            Kết nối account
          </Button>
        </div>
        {bots.isLoading ? (
          <Skeleton className="h-[220px] rounded-[10px]" />
        ) : (
          <BotAccountsTable data={bots.data ?? []} />
        )}
      </section>
    </div>
  );
}
