import type { LucideIcon } from 'lucide-react';
import { StatusDot } from '@/components/status-dot';
import type { Slot } from './api';

export function SlotCard({ slot, icon: Icon }: { slot: Slot; icon: LucideIcon }) {
  const status =
    slot.status === 'active' ? 'ok' :
    slot.status === 'fallback' ? 'warn' : 'warn';
  const statusLabel =
    slot.status === 'active' ? 'Hoạt động' :
    slot.status === 'fallback' ? 'Fallback' : 'Thiếu cấu hình';

  return (
    <div className="rounded-[10px] bg-card p-4 shadow-[0_0_0_1px_hsl(var(--border-strong)),0_1px_2px_rgba(0,0,0,.04)] transition-transform hover:-translate-y-[1px]">
      <div className="h-[30px] w-[30px] rounded-[7px] bg-muted grid place-items-center text-primary mb-3.5">
        <Icon className="h-[15px] w-[15px]" strokeWidth={1.8} />
      </div>
      <div className="text-[10.5px] uppercase tracking-wider text-[hsl(var(--dim))] font-medium mb-1 capitalize">{slot.slot}</div>
      <div className={`text-[15px] font-medium tracking-tight ${!slot.model ? 'text-muted-foreground' : ''}`}>
        {slot.model ?? 'Chưa cấu hình'}
      </div>
      <div className="text-xs text-muted-foreground mt-0.5 mb-4">
        {slot.provider ?? 'Fallback → Smart slot'}
      </div>
      <div className="flex items-center justify-between pt-3.5 border-t border-border text-xs">
        <StatusDot status={status as any} label={statusLabel} />
        <a className="text-primary font-medium hover:underline underline-offset-[3px] cursor-pointer">
          {slot.status === 'missing' ? 'Thiết lập' : 'Đổi'}
        </a>
      </div>
    </div>
  );
}
