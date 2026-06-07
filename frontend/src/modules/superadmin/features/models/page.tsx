import { Link } from 'react-router-dom';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { SlotsTab } from './slots-tab';
import { ModelsTab } from './models-tab';
import { RoutesTab } from './routes-tab';
import { BudgetsTab } from './budgets-tab';

export default function ModelsPage() {
  return (
    <PageWrap>
      <PageHeader
        title="Models AI"
        subtitle="Quản lý model, routing và budget toàn hệ thống."
      />

      <PageSection>
        <Tabs defaultValue="slots">
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
      </PageSection>

      <PageSection className="rounded-[12px] border border-dashed border-border px-5 py-4 flex items-center justify-between gap-4 text-sm">
        <div>
          <span className="font-medium">Tài khoản bot</span>
          <span className="text-muted-foreground ml-2">
            Tài khoản Zalo cá nhân và Telegram bot phục vụ các boss.
          </span>
        </div>
        <Link
          to="/app/superadmin/bot-accounts"
          className="text-sm font-medium text-[hsl(var(--primary))] underline underline-offset-2 hover:no-underline whitespace-nowrap"
        >
          Quản lý tài khoản bot →
        </Link>
      </PageSection>
    </PageWrap>
  );
}
