import { useState } from 'react';
import { useSuspenseQuery } from '@tanstack/react-query';
import { Bell, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { EmptyState } from '@/components/empty-state';
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
    <div className="flex flex-col gap-6 p-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Nhắc lịch</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Quản lý các nhắc lịch cá nhân và nhóm
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Tạo nhắc lịch
        </Button>
      </div>

      {/* Tabs + table */}
      <Tabs value={activeTab} onValueChange={v => setActiveTab(v as TabValue)}>
        <TabsList>
          {TABS.map(t => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <div className="mt-4 rounded-md border bg-card">
          <RemindersList status={activeTab} />
        </div>
      </Tabs>

      <CreateReminderDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
