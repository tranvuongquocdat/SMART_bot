import { useState } from 'react';
import { useSuspenseQuery } from '@tanstack/react-query';
import { Bell, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { EmptyState } from '@/components/empty-state';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { CreateReminderDialog } from './create-dialog';
import { ReminderRow } from './reminder-row';
import { remindersQuery } from './api';

const TABS = [
  { value: 'pending', label: 'Đang chờ' },
  { value: 'done', label: 'Đã xong' },
  { value: 'all', label: 'Tất cả' },
] as const;

type TabValue = (typeof TABS)[number]['value'];

function RemindersList({ status }: { status: TabValue }) {
  const { data: reminders } = useSuspenseQuery(remindersQuery(status));

  if (reminders.length === 0) {
    return (
      <EmptyState
        icon={Bell}
        title="Chưa có nhắc lịch nào"
        description={
          status === 'pending'
            ? 'Tạo nhắc lịch mới để không bỏ lỡ việc quan trọng.'
            : 'Không có nhắc lịch nào khớp với bộ lọc này.'
        }
      />
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-muted-foreground border-b">
          <th className="p-3 w-10"></th>
          <th className="p-3">Nội dung</th>
          <th className="p-3 whitespace-nowrap">Thời gian</th>
          <th className="p-3">Trạng thái</th>
          <th className="p-3">Phạm vi</th>
          <th className="p-3 w-12"></th>
        </tr>
      </thead>
      <tbody>
        {reminders.map(r => (
          <ReminderRow key={r.id} reminder={r} activeStatus={status} />
        ))}
      </tbody>
    </table>
  );
}

export default function RemindersPage() {
  const [activeTab, setActiveTab] = useState<TabValue>('pending');
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <PageWrap>
      <PageHeader
        title="Nhắc nhở"
        subtitle="Quản lý các nhắc lịch cá nhân và nhóm"
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            Tạo nhắc lịch
          </Button>
        }
      />

      <PageSection>
        <Tabs value={activeTab} onValueChange={v => setActiveTab(v as TabValue)}>
          <TabsList>
            {TABS.map(t => (
              <TabsTrigger key={t.value} value={t.value}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <div className="mt-4 rounded-[12px] bg-card-grad surface-section overflow-hidden">
            <RemindersList status={activeTab} />
          </div>
        </Tabs>
      </PageSection>

      <CreateReminderDialog open={createOpen} onOpenChange={setCreateOpen} />
    </PageWrap>
  );
}
