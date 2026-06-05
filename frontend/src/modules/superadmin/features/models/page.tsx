import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { BotAccountsTable } from './bot-accounts-table';
import { SlotsTab } from './slots-tab';
import { ModelsTab } from './models-tab';
import { RoutesTab } from './routes-tab';
import { BudgetsTab } from './budgets-tab';
import { botAccountsQuery } from './api';

export default function ModelsPage() {
  const bots = useQuery(botAccountsQuery);

  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1140px]">
      <header className="mb-8">
        <h1 className="text-[24px] font-semibold tracking-tight">Models &amp; Bots</h1>
        <p className="text-muted-foreground mt-1.5">
          Quản lý model, routing, budget và bot account toàn hệ thống.
        </p>
      </header>

      <Tabs defaultValue="slots" className="mb-6">
        <TabsList>
          <TabsTrigger value="slots">Slots</TabsTrigger>
          <TabsTrigger value="models">Models</TabsTrigger>
          <TabsTrigger value="routes">LLM routes</TabsTrigger>
          <TabsTrigger value="budgets">Budgets</TabsTrigger>
        </TabsList>

        <TabsContent value="slots" className="mt-6">
          <SlotsTab />
        </TabsContent>

        <TabsContent value="models" className="mt-6">
          <ModelsTab />
        </TabsContent>

        <TabsContent value="routes" className="mt-6">
          <RoutesTab />
        </TabsContent>

        <TabsContent value="budgets" className="mt-6">
          <BudgetsTab />
        </TabsContent>
      </Tabs>

      {/* Bot accounts — will move to its own page in SP2-9 */}
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
