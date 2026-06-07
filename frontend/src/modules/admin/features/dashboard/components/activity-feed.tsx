import { motion } from 'framer-motion';
import { BarChart2 } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { fadeUp } from '@/lib/motion';

type Activity = { kind: string; id: number; title: string; status: string; ts: string };

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s trước`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}p trước`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h trước`;
  const d = Math.floor(h / 24);
  return `${d}d trước`;
}

function kindLabel(kind: string): string {
  if (kind === 'action_item') return 'việc';
  if (kind === 'reminder') return 'nhắc';
  return kind;
}

export function ActivityFeed({ items }: { items: Activity[] }) {
  return (
    <motion.div variants={fadeUp}>
      <Card>
        <CardHeader>
          <CardTitle>Hoạt động gần đây</CardTitle>
          <Badge variant="live">Realtime</Badge>
        </CardHeader>
        <CardBody className="p-0">
          {items.length === 0 ? (
            <div className="flex flex-col items-center py-8 gap-2">
              <BarChart2 className="h-7 w-7 text-muted-foreground/30" />
              <p className="text-[12px] text-muted-foreground">Chưa có hoạt động nào</p>
            </div>
          ) : (
            <ul>
              {items.map((a, i) => (
                <li
                  key={`${a.kind}-${a.id}-${i}`}
                  className={
                    'flex items-center gap-3 px-[14px] py-[9px] ' +
                    'transition-[background-color,transform] duration-150 hover:translate-x-[2px] hover:bg-[hsl(var(--hover))] ' +
                    (i < items.length - 1 ? 'border-row' : '')
                  }
                >
                  <Badge variant="secondary">{kindLabel(a.kind)}</Badge>
                  <span className="text-[12.5px] truncate flex-1">{a.title}</span>
                  <span className="text-[10.5px] text-muted-foreground shrink-0 tabular-nums">
                    {relativeTime(a.ts)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </motion.div>
  );
}
