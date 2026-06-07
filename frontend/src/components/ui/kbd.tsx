import * as React from 'react';
import { cn } from '@/lib/utils';

export const Kbd = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(
  ({ className, children, ...props }, ref) => (
    <kbd
      ref={ref}
      className={cn(
        'inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-[4px]',
        'border border-border bg-muted px-1 font-mono text-[10px] text-[hsl(var(--dim))]',
        className
      )}
      {...props}
    >
      {children}
    </kbd>
  )
);
Kbd.displayName = 'Kbd';
