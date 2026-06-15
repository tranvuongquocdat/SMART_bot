import { motion } from 'framer-motion';
import { BarChart2 } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { fadeUp } from '@/lib/motion';
import { useT } from '@/lib/i18n';
import { relativeTimeT } from '@/lib/relative-time';

type Activity = { kind: string; id: number; title: string; status: string; ts: string };

export function ActivityFeed({ items }: { items: Activity[] }) {
  const t = useT();
  const kindLabel = (kind: string) =>
    kind === 'action_item'
      ? t('dash.kind.actionItem')
      : kind === 'reminder'
        ? t('dash.kind.reminder')
        : kind;
  return (
    <motion.div variants={fadeUp}>
      <Card>
        <CardHeader>
          <CardTitle>{t('dash.activity')}</CardTitle>
          <Badge variant="live">{t('dash.realtime')}</Badge>
        </CardHeader>
        <CardBody className="p-0">
          {items.length === 0 ? (
            <div className="flex flex-col items-center py-8 gap-2">
              <BarChart2 className="h-7 w-7 text-muted-foreground/30" />
              <p className="text-[12px] text-muted-foreground">{t('dash.noActivity')}</p>
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
                    {relativeTimeT(a.ts, t)}
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
