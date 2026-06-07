import { motion } from 'framer-motion';
import { Users } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { fadeUp } from '@/lib/motion';

type Group = {
  id: number;
  name: string;
  provider: string;
  msg_count_7d: number;
  updated_at: string;
};

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

export function RecentGroups({ groups }: { groups: Group[] }) {
  return (
    <motion.div variants={fadeUp}>
      <Card>
        <CardHeader>
          <CardTitle>Nhóm gần đây</CardTitle>
          <span className="text-[10px] text-[hsl(var(--dim))]">{groups.length} nhóm</span>
        </CardHeader>
        <CardBody>
          {groups.length === 0 ? (
            <div className="flex flex-col items-center py-8 gap-2">
              <Users className="h-7 w-7 text-muted-foreground/30" />
              <p className="text-[12px] text-muted-foreground">Chưa có nhóm nào</p>
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {groups.map((g) => (
                <li
                  key={g.id}
                  className="py-2 flex items-center justify-between gap-2 transition-transform hover:translate-x-[2px]"
                >
                  <div className="min-w-0">
                    <div className="text-[12.5px] font-medium truncate">{g.name}</div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">
                      {relativeTime(g.updated_at)}
                    </div>
                  </div>
                  <Badge variant="secondary">{g.provider}</Badge>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </motion.div>
  );
}
