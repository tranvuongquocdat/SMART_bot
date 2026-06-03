import { FileText, Link as LinkIcon, Image as ImageIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { formatNumber, relativeTime } from '@/lib/format';
import { StatusDot } from '@/components/status-dot';
import type { Stats, Member, FileItem } from './api';

export function RightPanel({ stats, members, files }: { stats?: Stats; members?: Member[]; files?: FileItem[] }) {
  return (
    <aside className="flex flex-col gap-4 sticky top-[90px] self-start">
      <Card title="7 ngày qua">
        <div className="grid grid-cols-2 gap-3">
          <Stat label="Tin nhắn" value={stats?.messages} />
          <Stat label="Tác vụ" value={stats?.tasks} />
          <Stat label="Nhắc lịch" value={stats?.reminders} />
          <Stat label="Quyết định" value={stats?.decisions} />
        </div>
      </Card>
      <Card title={`Thành viên (${members?.length ?? 0})`}>
        {(members?.length ?? 0) === 0 && <p className="text-xs text-muted-foreground">Chưa có dữ liệu thành viên.</p>}
        {members?.map((m, i) => (
          <div key={m.id} className={`flex items-center gap-2.5 py-1.5 ${i > 0 ? 'border-t border-border' : ''}`}>
            <div className="h-[26px] w-[26px] rounded-full bg-gradient-to-br from-[hsl(168_60%_40%)] to-[hsl(220_50%_35%)] text-white text-[10.5px] font-medium tracking-tight grid place-items-center shrink-0">
              {(m.name[0] || '?').toUpperCase()}
            </div>
            <div className="text-[12.5px] flex-1 min-w-0">
              {m.name} {m.role && <span className="text-[11px] text-[hsl(var(--dim))]">· {m.role}</span>}
            </div>
            <StatusDot status={m.last_seen_at ? 'ok' : 'idle'} />
          </div>
        ))}
      </Card>
      <Card title="Tệp & link gần đây">
        <div className="flex flex-col gap-2.5 text-[13px]">
          {(files?.length ?? 0) === 0 && <p className="text-xs text-muted-foreground">Chưa có tệp nào.</p>}
          {files?.map(f => {
            const Icon = f.kind === 'image' ? ImageIcon : f.kind === 'link' ? LinkIcon : FileText;
            return (
              <div key={f.id} className="flex items-center gap-2 min-w-0">
                <Icon className="h-3.5 w-3.5 shrink-0 text-[hsl(var(--info))]" strokeWidth={2} />
                <span className="truncate">{f.name}</span>
                <span className="text-[11px] text-[hsl(var(--dim))] ml-auto shrink-0">{relativeTime(f.created_at)}</span>
              </div>
            );
          })}
        </div>
      </Card>
    </aside>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-[10px] bg-card p-4 shadow-[0_0_0_1px_hsl(var(--border-strong)),0_1px_2px_rgba(0,0,0,.04)]">
      <h3 className="text-[11px] uppercase tracking-wider text-[hsl(var(--dim))] font-medium mb-3">{title}</h3>
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div>
      <p className="text-xl font-semibold tracking-tight leading-tight">{value !== undefined ? formatNumber(value) : '—'}</p>
      <p className="text-[11px] text-muted-foreground mt-0.5">{label}</p>
    </div>
  );
}
