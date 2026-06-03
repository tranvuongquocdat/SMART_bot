import { cn } from '@/lib/utils';

type Status = 'ok' | 'warn' | 'err' | 'idle';

const COLORS: Record<Status, string> = {
  ok: 'bg-[hsl(var(--ok))] ring-[hsl(var(--ok)/0.12)]',
  warn: 'bg-[hsl(var(--warn))] ring-[hsl(var(--warn)/0.12)]',
  err: 'bg-[hsl(var(--danger))] ring-[hsl(var(--danger)/0.12)]',
  idle: 'bg-[hsl(var(--dim))] ring-transparent',
};

const TEXT: Record<Status, string> = {
  ok: 'text-[hsl(var(--ok))]',
  warn: 'text-[hsl(var(--warn))]',
  err: 'text-[hsl(var(--danger))]',
  idle: 'text-muted-foreground',
};

export function StatusDot({
  status,
  label,
  className,
}: {
  status: Status;
  label?: string;
  className?: string;
}) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-xs', TEXT[status], className)}>
      <span className={cn('h-1.5 w-1.5 rounded-full ring-[3px]', COLORS[status])} />
      {label}
    </span>
  );
}
