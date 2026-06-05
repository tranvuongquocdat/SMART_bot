import { Link } from 'react-router-dom';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { SlotsTab } from './slots-tab';
import { ModelsTab } from './models-tab';
import { RoutesTab } from './routes-tab';
import { BudgetsTab } from './budgets-tab';

export default function ModelsPage() {
  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1140px]">
      <header className="mb-8">
        <h1 className="text-[24px] font-semibold tracking-tight">Models</h1>
        <p className="text-muted-foreground mt-1.5">
          Quản lý model, routing và budget toàn hệ thống.
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

      {/* Bot accounts moved to dedicated page */}
      <div className="rounded-[10px] border border-dashed border-border px-5 py-4 flex items-center justify-between gap-4 text-sm">
        <div>
          <span className="font-medium">Bot accounts</span>
          <span className="text-muted-foreground ml-2">
            Tài khoản Zalo cá nhân và Telegram bot phục vụ các boss.
          </span>
        </div>
        <Link
          to="/app/superadmin/bot-accounts"
          className="text-sm font-medium underline underline-offset-2 hover:no-underline whitespace-nowrap"
        >
          Quản lý bot accounts →
        </Link>
      </div>
    </div>
  );
}
