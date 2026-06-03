import type { LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6">
      <Icon className="h-10 w-10 text-[hsl(var(--dim))] mb-3" strokeWidth={1.5} />
      <h3 className="text-base font-medium tracking-tight">{title}</h3>
      {description && (
        <p className="text-sm text-muted-foreground mt-1 max-w-sm">{description}</p>
      )}
      {action && (
        <Button onClick={action.onClick} className="mt-5">
          {action.label}
        </Button>
      )}
    </div>
  );
}
