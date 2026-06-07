import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-[12.5px] font-medium',
    'transition-[transform,background-color,box-shadow,color] duration-150',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.55)]',
    'active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50',
    '[&_svg]:pointer-events-none [&_svg]:size-3.5 [&_svg]:shrink-0',
  ].join(' '),
  {
    variants: {
      variant: {
        default:
          'bg-accent-gradient text-[hsl(var(--primary-foreground))] shadow-pop hover:-translate-y-[1px]',
        destructive:
          'bg-[hsl(var(--danger))] text-white shadow-pop hover:-translate-y-[1px]',
        outline:
          'border border-border bg-transparent text-foreground hover:bg-[hsl(var(--hover))] hover:-translate-y-[1px]',
        secondary:
          'bg-[hsl(var(--muted))] text-foreground hover:bg-[hsl(var(--hover))]',
        ghost: 'hover:bg-[hsl(var(--hover))] text-foreground',
        link: 'text-[hsl(var(--primary))] underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-8 px-3',
        sm: 'h-7 px-2.5 text-[11px]',
        lg: 'h-9 px-4',
        icon: 'h-8 w-8',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size, className }))} {...props} />;
  }
);
Button.displayName = 'Button';

export { Button, buttonVariants };
