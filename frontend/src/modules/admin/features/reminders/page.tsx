import { useState } from 'react';
import { useSuspenseQuery } from '@tanstack/react-query';
import { Bell, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { EmptyState } from '@/components/empty-state';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { useT } from '@/lib/i18n';
import { CreateReminderDialog } from './create-dialog';
import { ReminderRow } from './reminder-row';
import { remindersQuery } from './api';

const TAB_VALUES = ['pending', 'done', 'all'] as const;
type TabValue = (typeof TAB_VALUES)[number];

function RemindersList({ status }: { status: TabValue }) {
  const t = useT();
  const { data: reminders } = useSuspenseQuery(remindersQuery(status));

  if (reminders.length === 0) {
    return (
      <EmptyState
        icon={Bell}
        title={t('rem.empty.title')}
        description={status === 'pending' ? t('rem.empty.pending') : t('rem.empty.filtered')}
      />
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-muted-foreground border-b">
          <th className="p-3 w-10"></th>
          <th className="p-3">{t('rem.col.content')}</th>
          <th className="p-3 whitespace-nowrap">{t('rem.col.time')}</th>
          <th className="p-3">{t('rem.col.status')}</th>
          <th className="p-3">{t('rem.col.scope')}</th>
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
  const t = useT();
  const [activeTab, setActiveTab] = useState<TabValue>('pending');
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <PageWrap>
      <PageHeader
        title={t('rem.title')}
        subtitle={t('rem.subtitle')}
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            {t('rem.create')}
          </Button>
        }
      />

      <PageSection>
        <Tabs value={activeTab} onValueChange={v => setActiveTab(v as TabValue)}>
          <TabsList>
            {TAB_VALUES.map(v => (
              <TabsTrigger key={v} value={v}>
                {t(`rem.tab.${v}`)}
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
