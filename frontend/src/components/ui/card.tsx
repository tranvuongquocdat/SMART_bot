import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const cardVariants = cva(
  'rounded-[12px] border bg-card transition-colors',
  {
    variants: {
      variant: {
        default: 'border-border',
        glow: 'border-border relative overflow-hidden before:absolute before:inset-0 before:pointer-events-none before:bg-[radial-gradient(160px_90px_at_100%_100%,hsl(var(--primary)/0.18),transparent_70%)]',
      },
    },
    defaultVariants: { variant: 'default' },
  }
);

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant, ...props }, ref) => (
    <div ref={ref} className={cn(cardVariants({ variant }), className)} {...props} />
  )
);
Card.displayName = 'Card';

export const CardHeader = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('px-4 py-3 border-b border-border flex items-center justify-between gap-2', className)} {...p} />
);
export const CardTitle = ({ className, ...p }: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h3 className={cn('text-[13px] font-semibold tracking-tight', className)} {...p} />
);
export const CardBody = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('px-4 py-3', className)} {...p} />
);
