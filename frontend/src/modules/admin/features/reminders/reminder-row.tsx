import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { MoreHorizontal, Trash2, Clock, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { relativeTime } from '@/lib/format';
import { patchReminder, deleteReminder, remindersQuery, type Reminder } from './api';

function statusBadgeVariant(status: Reminder['status']): 'default' | 'secondary' | 'outline' {
  if (status === 'pending') return 'default';
  if (status === 'done') return 'secondary';
  return 'outline';
}

function addMinutes(isoStr: string, minutes: number): string {
  const d = new Date(isoStr);
  d.setMinutes(d.getMinutes() + minutes);
  return d.toISOString();
}

export function ReminderRow({
  reminder,
  activeStatus,
}: {
  reminder: Reminder;
  activeStatus: string;
}) {
  const qc = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);

  function invalidate() {
    qc.invalidateQueries(remindersQuery(activeStatus));
    qc.invalidateQueries(remindersQuery('all'));
    qc.invalidateQueries(remindersQuery('pending'));
    qc.invalidateQueries(remindersQuery('done'));
  }

  const patchMut = useMutation({
    mutationFn: (body: Partial<Pick<Reminder, 'status' | 'due_at'>>) =>
      patchReminder(reminder.id, body),
    onSuccess: () => {
      invalidate();
      toast.success('Đã cập nhật nhắc lịch');
    },
    onError: () => toast.error('Cập nhật thất bại'),
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteReminder(reminder.id),
    onSuccess: () => {
      invalidate();
      toast.success('Đã xoá nhắc lịch');
      setConfirmDelete(false);
    },
    onError: () => toast.error('Xoá thất bại'),
  });

  const isDone = reminder.status !== 'pending';

  return (
    <>
      <tr className="border-t hover:bg-muted/30 transition-colors">
        <td className="p-3 w-10">
          <Checkbox
            checked={isDone}
            disabled={patchMut.isPending}
            onCheckedChange={checked => {
              patchMut.mutate({ status: checked ? 'done' : 'pending' });
            }}
          />
        </td>
        <td className="p-3">
          <span className={isDone ? 'line-through text-muted-foreground' : ''}>
            {reminder.text}
          </span>
        </td>
        <td className="p-3 text-sm text-muted-foreground whitespace-nowrap">
          <span title={reminder.due_at}>{relativeTime(reminder.due_at)}</span>
        </td>
        <td className="p-3">
          <Badge variant={statusBadgeVariant(reminder.status)}>
            {reminder.status === 'pending'
              ? 'Đang chờ'
              : reminder.status === 'done'
              ? 'Đã xong'
              : 'Đã huỷ'}
          </Badge>
        </td>
        <td className="p-3 text-sm text-muted-foreground">
          {reminder.scope === 'group' ? 'Nhóm' : 'DM'}
        </td>
        <td className="p-3 text-right">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-7 w-7 p-0">
                <MoreHorizontal className="h-4 w-4" />
                <span className="sr-only">Tuỳ chọn</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {reminder.status === 'pending' && (
                <>
                  <DropdownMenuItem
                    onClick={() =>
                      patchMut.mutate({ status: 'done' })
                    }
                  >
                    <CheckCircle2 className="mr-2 h-4 w-4" />
                    Đánh dấu xong
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={() =>
                      patchMut.mutate({
                        due_at: addMinutes(reminder.due_at, 30),
                      })
                    }
                  >
                    <Clock className="mr-2 h-4 w-4" />
                    Nhắc lại sau 30 phút
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() =>
                      patchMut.mutate({
                        due_at: addMinutes(reminder.due_at, 60),
                      })
                    }
                  >
                    <Clock className="mr-2 h-4 w-4" />
                    Nhắc lại sau 1 giờ
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() =>
                      patchMut.mutate({
                        due_at: addMinutes(reminder.due_at, 60 * 24),
                      })
                    }
                  >
                    <Clock className="mr-2 h-4 w-4" />
                    Nhắc lại sau 1 ngày
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                </>
              )}
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Xoá
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </td>
      </tr>

      {/* Delete confirmation dialog */}
      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Xác nhận xoá nhắc lịch</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground mt-1">
            Nhắc lịch "{reminder.text}" sẽ bị xoá vĩnh viễn. Hành động này không thể hoàn tác.
          </p>
          <DialogFooter className="mt-4">
            <Button
              variant="outline"
              onClick={() => setConfirmDelete(false)}
              disabled={deleteMut.isPending}
            >
              Huỷ
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteMut.mutate()}
              disabled={deleteMut.isPending}
            >
              {deleteMut.isPending ? 'Đang xoá...' : 'Xoá'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
