import { Users, MessageSquare, Clock, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatNumber, relativeTime } from '@/lib/format';
import type { Group } from './api';

const CHANNEL_LABEL: Record<string, string> = {
  zalo: 'Zalo', telegram: 'Telegram', lark: 'Lark', web: 'Web',
};

export function GroupHeader({ group }: { group: Group }) {
  const initials = group.name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase();
  return (
    <div className="flex items-start gap-4 mb-7 flex-wrap">
      <div className="h-[52px] w-[52px] rounded-xl bg-gradient-to-br from-[hsl(168_60%_35%)] to-[hsl(220_50%_30%)] text-white text-lg font-semibold tracking-tight grid place-items-center shrink-0 shadow-[0_0_0_1px_hsl(168_40%_20%),inset_0_1px_0_hsl(168_80%_70%/0.2)]">
        {initials}
      </div>
      <div className="flex-1 min-w-[220px]">
        <h1 className="flex items-center gap-2.5 text-[22px] font-semibold tracking-tight">
          {group.name}
          <span className="text-[10.5px] py-0.5 px-1.5 rounded bg-muted text-muted-foreground font-medium tracking-wide uppercase">
            {CHANNEL_LABEL[group.channel] ?? group.channel}
          </span>
        </h1>
        <div className="text-[13px] text-muted-foreground flex items-center gap-3 flex-wrap mt-0.5">
          <span className="inline-flex items-center gap-1.5"><Users className="h-3.5 w-3.5 text-[hsl(var(--dim))]" />{group.members_count} thành viên</span>
          <span className="inline-flex items-center gap-1.5"><MessageSquare className="h-3.5 w-3.5 text-[hsl(var(--dim))]" />{formatNumber(group.messages_30d)} tin nhắn / 30 ngày</span>
          <span className="inline-flex items-center gap-1.5"><Clock className="h-3.5 w-3.5 text-[hsl(var(--dim))]" />Hoạt động cuối: {relativeTime(group.last_active_at)}</span>
        </div>
      </div>
      <div className="flex gap-1.5">
        <Button variant="ghost" size="sm"><Download className="h-3.5 w-3.5" />Xuất</Button>
        <Button variant="outline" size="sm">Cấu hình nhóm</Button>
      </div>
    </div>
  );
}
