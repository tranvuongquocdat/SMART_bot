import { motion } from 'framer-motion';
import { Users } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { fadeUp } from '@/lib/motion';
import { useT } from '@/lib/i18n';
import { relativeTimeT } from '@/lib/relative-time';

function providerVariant(p: string): 'zalo' | 'telegram' | 'secondary' {
  if (p === 'zalo') return 'zalo';
  if (p === 'telegram') return 'telegram';
  return 'secondary';
}

type Group = {
  id: number;
  name: string;
  provider: string;
  msg_count_7d: number;
  updated_at: string;
};

export function RecentGroups({ groups }: { groups: Group[] }) {
  const t = useT();
  return (
    <motion.div variants={fadeUp}>
      <Card>
        <CardHeader>
          <CardTitle>{t('dash.recentGroups')}</CardTitle>
          <span className="text-[10px] text-[hsl(var(--dim))]">
            {t('dash.groupsCount', { n: groups.length })}
          </span>
        </CardHeader>
        <CardBody className="p-0">
          {groups.length === 0 ? (
            <div className="flex flex-col items-center py-8 gap-2">
              <Users className="h-7 w-7 text-muted-foreground/30" />
              <p className="text-[12px] text-muted-foreground">{t('dash.noGroups')}</p>
            </div>
          ) : (
            <ul>
              {groups.map((g, i) => (
                <li
                  key={g.id}
                  className={
                    'flex items-center justify-between gap-3 px-[14px] py-[9px] ' +
                    'transition-[background-color,transform] duration-150 hover:translate-x-[2px] hover:bg-[hsl(var(--hover))] ' +
                    (i < groups.length - 1 ? 'border-row' : '')
                  }
                >
                  <div className="min-w-0">
                    <div className="text-[12.5px] truncate">{g.name}</div>
                    <div className="text-[10.5px] text-[hsl(var(--dim))] mt-0.5">
                      {relativeTimeT(g.updated_at, t)}
                    </div>
                  </div>
                  <Badge variant={providerVariant(g.provider)}>{g.provider}</Badge>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </motion.div>
  );
}
