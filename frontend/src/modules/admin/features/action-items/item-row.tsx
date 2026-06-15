import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { relativeTime } from '@/lib/format';
import { useT } from '@/lib/i18n';
import { patchActionItem, actionItemsQuery, type ActionItem, type ActionItemFilters } from './api';

export function ItemRow({
  item,
  filters,
}: {
  item: ActionItem;
  filters: ActionItemFilters;
}) {
  const t = useT();
  const qc = useQueryClient();

  const patchMut = useMutation({
    mutationFn: (done: boolean) => patchActionItem(item.id, { done }),
    onSuccess: () => {
      qc.invalidateQueries(actionItemsQuery(filters));
      qc.invalidateQueries(actionItemsQuery({}));
      toast.success(t('common.updated'));
    },
    onError: () => toast.error(t('common.updateError')),
  });

  const isDone = item.status === 'done';

  return (
    <tr className="border-t hover:bg-muted/30 transition-colors">
      <td className="p-3 w-10">
        <Checkbox
          checked={isDone}
          disabled={patchMut.isPending}
          onCheckedChange={checked => patchMut.mutate(!!checked)}
        />
      </td>
      <td className="p-3">
        <span className={isDone ? 'line-through text-muted-foreground' : ''}>{item.text}</span>
      </td>
      <td className="p-3 text-sm text-muted-foreground">{item.group_name}</td>
      <td className="p-3 text-sm text-muted-foreground">{item.assignee_name ?? '—'}</td>
      <td className="p-3 text-sm text-muted-foreground whitespace-nowrap">
        {item.due_at ? (
          <span title={item.due_at}>{relativeTime(item.due_at)}</span>
        ) : (
          '—'
        )}
      </td>
      <td className="p-3">
        <Badge variant={isDone ? 'secondary' : 'default'}>
          {isDone ? t('ai.status.done') : t('ai.status.doing')}
        </Badge>
      </td>
    </tr>
  );
}
