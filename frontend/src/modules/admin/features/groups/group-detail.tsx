import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { LoaderFunction } from 'react-router-dom';
import type { QueryClient } from '@tanstack/react-query';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
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
          <TabsTrigger value="summary">Tóm tắt</TabsTrigger>
          <TabsTrigger value="timeline">Dòng thời gian</TabsTrigger>
          <TabsTrigger value="tasks">Tác vụ ({stats.data?.tasks ?? 0})</TabsTrigger>
          <TabsTrigger value="reminders">Nhắc lịch ({stats.data?.reminders ?? 0})</TabsTrigger>
          <TabsTrigger value="decisions">Quyết định ({stats.data?.decisions ?? 0})</TabsTrigger>
          <TabsTrigger value="files">Tệp &amp; link</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="grid grid-cols-[1fr_320px] gap-7 max-w-[1240px] max-md:grid-cols-1">
        <div>
          {summary.data && <SummaryCard summary={summary.data} />}
          <div className="flex items-center justify-between mt-7 mb-3.5">
            <h2 className="text-[13.5px] font-semibold tracking-tight">Mục được trích xuất hôm nay</h2>
          </div>
          {items.data && <ItemsList items={items.data} />}
          <div className="flex items-center justify-between mt-7 mb-3.5">
            <h2 className="text-[13.5px] font-semibold tracking-tight">Dòng thời gian</h2>
          </div>
          {timeline.data && <TimelineCard messages={timeline.data.messages} />}
        </div>
        <RightPanel stats={stats.data} members={members.data} files={files.data} />
      </div>
    </div>
  );
}
