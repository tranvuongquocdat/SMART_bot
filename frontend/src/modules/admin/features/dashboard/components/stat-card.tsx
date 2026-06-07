import { useEffect, useState } from 'react';
import { motion, useMotionValue, animate, useReducedMotion } from 'framer-motion';
import { Card } from '@/components/ui/card';
import { ease, fadeUp } from '@/lib/motion';
import { cn } from '@/lib/utils';

type Props = { label: string; value: number; previous: number };

function formatDelta(
  current: number,
  previous: number,
): { text: string; tone: 'up' | 'down' | 'flat' | 'new' } {
  if (previous === 0 && current === 0) return { text: '→ 0%', tone: 'flat' };
  if (previous === 0) return { text: 'Mới', tone: 'new' };
  const pct = Math.round(((current - previous) / previous) * 100);
  if (pct > 0) return { text: `↗ +${pct}%`, tone: 'up' };
  if (pct < 0) return { text: `↘ ${pct}%`, tone: 'down' };
  return { text: '→ 0%', tone: 'flat' };
}

export function StatCard({ label, value, previous }: Props) {
  const reduce = useReducedMotion();
  const mv = useMotionValue(reduce ? value : 0);
  const [display, setDisplay] = useState(reduce ? value : 0);
  const delta = formatDelta(value, previous);

  useEffect(() => {
    if (reduce) {
      setDisplay(value);
      return;
    }
    const controls = animate(mv, value, {
      duration: 1.0,
      ease,
      onUpdate: (v) => setDisplay(Math.round(v)),
    });
    return () => controls.stop();
  }, [value, reduce, mv]);

  return (
    <motion.div variants={fadeUp}>
      <Card variant="glow" className="px-4 py-3.5 relative">
        <div className="absolute left-0 right-0 top-0 h-px bg-accent-gradient opacity-50" />
        <div className="text-[10px] uppercase tracking-wider text-[hsl(var(--dim))] font-medium">
          {label}
        </div>
        <div className="text-[22px] font-semibold tracking-tight mt-1 tabular-nums">
          {display.toLocaleString('vi-VN')}
        </div>
        <div
          className={cn(
            'text-[10px] mt-0.5 tabular-nums font-medium',
            delta.tone === 'up' && 'text-[hsl(var(--ok))]',
            delta.tone === 'down' && 'text-[hsl(var(--danger))]',
            delta.tone === 'flat' && 'text-[hsl(var(--dim))]',
            delta.tone === 'new' && 'text-[hsl(var(--primary))]',
          )}
        >
          {delta.text} <span className="text-[hsl(var(--dim))] font-normal">vs 30d trước</span>
        </div>
      </Card>
    </motion.div>
  );
}
