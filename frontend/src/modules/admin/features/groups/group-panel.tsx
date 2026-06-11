import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, Users, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { SummaryCard } from './summary-card';
import { ItemsList } from './items-list';
import { TimelineCard } from './timeline-card';
import { groupQuery, summaryQuery, itemsQuery, timelineQuery, statsQuery } from './api';

function ChannelChip({ channel }: { channel: string }) {
  if (channel === 'zalo') return <Badge variant="zalo">{channel}</Badge>;
  if (channel === 'telegram') return <Badge variant="telegram">{channel}</Badge>;
  return <Badge variant="secondary">{channel}</Badge>;
}

/**
 * Panel chi tiết nhóm nhúng cạnh danh sách (split view) — quản lý nhanh
 * không rời trang, chuyển nhóm khác chỉ là click row bên trái.
 */
export function GroupPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const group = useQuery(groupQuery(id));
  const summary = useQuery(summaryQuery(id));
  const items = useQuery(itemsQuery(id));
  const timeline = useQuery(timelineQuery(id));
  const stats = useQuery(statsQuery(id));

  return (
    <div className="rounded-xl border bg-card/40 flex flex-col min-h-0 sticky top-4 max-h-[calc(100vh-96px)]">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b shrink-0">
        {group.isLoading ? (
          <Skeleton className="h-5 w-40" />
        ) : (
          <>
            <p className="font-semibold truncate">{group.data?.name}</p>
            {group.data && <ChannelChip channel={group.data.channel} />}
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Users className="h-3.5 w-3.5" />
              {group.data?.members_count ?? 0}
            </span>
          </>
        )}
        <div className="ml-auto flex items-center gap-1">
          <Link
            to={`/app/admin/groups/${id}`}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors px-2 py-1"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Trang đầy đủ
          </Link>
          <button
            className="text-muted-foreground hover:text-foreground transition-colors p-1"
            onClick={onClose}
            aria-label="Đóng panel"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Stats strip */}
      {stats.data && (
        <div className="grid grid-cols-4 divide-x border-b text-center shrink-0">
          {[
            { label: 'Tin nhắn', value: stats.data.messages },
            { label: 'Tác vụ', value: stats.data.tasks },
            { label: 'Nhắc lịch', value: stats.data.reminders },
            { label: 'Quyết định', value: stats.data.decisions },
          ].map((s) => (
            <div key={s.label} className="py-2">
              <p className="text-sm font-semibold tabular-nums">{s.value}</p>
              <p className="text-[10px] text-muted-foreground">{s.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5 min-h-0">
        {summary.data && <SummaryCard summary={summary.data} />}
        <div>
          <h3 className="text-[13px] font-semibold mb-2.5">Mục được trích xuất hôm nay</h3>
          {items.data && <ItemsList items={items.data} />}
        </div>
        <div>
          <h3 className="text-[13px] font-semibold mb-2.5">Dòng thời gian</h3>
          {timeline.data && <TimelineCard messages={timeline.data.messages} />}
        </div>
      </div>
    </div>
  );
}
