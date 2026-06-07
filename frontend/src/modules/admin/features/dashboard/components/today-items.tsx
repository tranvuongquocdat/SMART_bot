import { motion } from 'framer-motion';
import { ClipboardList } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/card';
import { fadeUp } from '@/lib/motion';

type Item = {
  id: number;
  text: string;
  due_at: string | null;
  status: string;
  assignee_name: string | null;
  group_name: string;
};

function formatDue(iso: string): string {
  const due = new Date(iso);
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const dayDiff = Math.floor((due.getTime() - startToday) / 86_400_000);
  const hhmm = due.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
  if (dayDiff < 0) return `Trễ · ${hhmm}`;
  if (dayDiff === 0) return hhmm;
  if (dayDiff === 1) return `Mai · ${hhmm}`;
  if (dayDiff < 7) return `${dayDiff}d sau`;
  return due.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' });
}

export function TodayItems({ items }: { items: Item[] }) {
  return (
    <motion.div variants={fadeUp}>
      <Card>
        <CardHeader>
          <CardTitle>Việc cần làm hôm nay</CardTitle>
          <span className="text-[10px] text-[hsl(var(--dim))]">{items.length} việc</span>
        </CardHeader>
        <CardBody className="p-0">
          {items.length === 0 ? (
            <div className="flex flex-col items-center py-8 gap-2">
              <ClipboardList className="h-7 w-7 text-muted-foreground/30" />
              <p className="text-[12px] text-muted-foreground">Hôm nay rảnh, nghỉ thôi.</p>
            </div>
          ) : (
            <ul>
              {items.map((it, i) => (
                <li
                  key={it.id}
                  className={
                    'flex items-center justify-between gap-3 px-[14px] py-[9px] ' +
                    'transition-[background-color,transform] duration-150 hover:translate-x-[2px] hover:bg-[hsl(var(--hover))] ' +
                    (i < items.length - 1 ? 'border-row' : '')
                  }
                >
                  <div className="min-w-0">
                    <div className="text-[12.5px] truncate">{it.text}</div>
                    <div className="text-[10.5px] text-[hsl(var(--dim))] mt-0.5 truncate">
                      {it.group_name}
                      {it.assignee_name && ` · ${it.assignee_name}`}
                    </div>
                  </div>
                  {it.due_at && (
                    <span className="text-[10.5px] text-muted-foreground shrink-0 tabular-nums">
                      {formatDue(it.due_at)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </motion.div>
  );
}
