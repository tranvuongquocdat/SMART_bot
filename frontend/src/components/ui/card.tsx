import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const cardVariants = cva(
  'rounded-[12px] bg-card-grad transition-shadow overflow-hidden',
  {
    variants: {
      variant: {
        default: 'surface-section',
        stat:    'surface-card relative hover:surface-stat-hover hover:-translate-y-px transition-transform',
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
  <div className={cn('px-[14px] py-[11px] flex items-center justify-between gap-2 border-row', className)} {...p} />
);
export const CardTitle = ({ className, ...p }: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h3 className={cn('text-[13px] font-semibold tracking-tight', className)} {...p} />
);
export const CardBody = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('px-[14px] py-1', className)} {...p} />
);
