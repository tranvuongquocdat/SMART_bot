import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-[4px] px-1.5 py-[1px] text-[10px] font-medium tabular-nums',
  {
    variants: {
      variant: {
        default: 'bg-[hsl(var(--primary-soft))] text-[hsl(var(--primary))]',
        secondary: 'bg-[hsl(var(--muted))] text-muted-foreground',
        outline: 'border border-border text-muted-foreground',
        destructive: 'bg-[hsl(var(--danger)/0.15)] text-[hsl(var(--danger))]',
        live: 'bg-[hsl(var(--primary-soft))] text-[hsl(var(--primary))]',
      },
    },
    defaultVariants: { variant: 'default' },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, children, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props}>
      {variant === 'live' && (
        <span className="relative inline-flex h-1.5 w-1.5">
          <span className="absolute inset-0 rounded-full bg-[hsl(var(--primary))] opacity-60 animate-ping" />
          <span className="relative rounded-full bg-[hsl(var(--primary))] h-1.5 w-1.5" />
        </span>
      )}
      {children}
    </div>
  );
}

export { Badge, badgeVariants };
