import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { LoaderFunction } from 'react-router-dom';
import type { QueryClient } from '@tanstack/react-query';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { useT } from '@/lib/i18n';
import { GroupHeader } from './group-header';
import { SummaryCard } from './summary-card';
import { ItemsList } from './items-list';
import { TimelineCard } from './timeline-card';
import { RightPanel } from './right-panel';
import {
  groupQuery, summaryQuery, itemsQuery, timelineQuery, statsQuery, membersQuery, filesQuery,
} from './api';

export const groupDetailLoader = (qc: QueryClient): LoaderFunction => async ({ params }) => {
  const id = params.groupId!;
  await qc.prefetchQuery(groupQuery(id));
  return { groupId: id };
};

export default function GroupDetail() {
  const t = useT();
  const { groupId } = useParams();
  const id = groupId!;
  const group = useQuery(groupQuery(id));
  const summary = useQuery(summaryQuery(id));
  const items = useQuery(itemsQuery(id));
  const timeline = useQuery(timelineQuery(id));
  const stats = useQuery(statsQuery(id));
  const members = useQuery(membersQuery(id));
  const files = useQuery(filesQuery(id));

  if (group.isLoading) {
    return <div className="p-10"><Skeleton className="h-32 w-full" /></div>;
  }
  if (!group.data) return null;

  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6">
      <GroupHeader group={group.data} />

      <Tabs defaultValue="summary" className="mb-6">
        <TabsList>
          <TabsTrigger value="summary">{t('grp.detailTab.summary')}</TabsTrigger>
          <TabsTrigger value="timeline">{t('grp.detailTab.timeline')}</TabsTrigger>
          <TabsTrigger value="tasks">{t('grp.detailTab.tasks')} ({stats.data?.tasks ?? 0})</TabsTrigger>
          <TabsTrigger value="reminders">{t('grp.detailTab.reminders')} ({stats.data?.reminders ?? 0})</TabsTrigger>
          <TabsTrigger value="decisions">{t('grp.detailTab.decisions')} ({stats.data?.decisions ?? 0})</TabsTrigger>
          <TabsTrigger value="files">{t('grp.detailTab.files')}</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="grid grid-cols-[1fr_320px] gap-7 max-w-[1240px] max-md:grid-cols-1">
        <div>
          {summary.data && <SummaryCard summary={summary.data} />}
          <div className="flex items-center justify-between mt-7 mb-3.5">
            <h2 className="text-[13.5px] font-semibold tracking-tight">{t('grp.detail.extractedToday')}</h2>
          </div>
          {items.data && <ItemsList items={items.data} />}
          <div className="flex items-center justify-between mt-7 mb-3.5">
            <h2 className="text-[13.5px] font-semibold tracking-tight">{t('grp.detailTab.timeline')}</h2>
          </div>
          {timeline.data && <TimelineCard messages={timeline.data.messages} />}
        </div>
        <RightPanel groupId={id} stats={stats.data} members={members.data} files={files.data} />
      </div>
    </div>
  );
}
