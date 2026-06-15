import { useState } from 'react';
import { FileText, Link as LinkIcon, Image as ImageIcon, MoreHorizontal, UserPlus } from 'lucide-react';
import type { ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { formatNumber, relativeTime } from '@/lib/format';
import { useT } from '@/lib/i18n';
import { StatusDot } from '@/components/status-dot';
import { UserPicker, type UserPickerOption } from '@/components/user-picker';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import type { Stats, Member, FileItem } from './api';
import { membersQuery, peopleSearchQuery, addMember, removeMember } from './api';

// ---------------------------------------------------------------------------
// Members panel (with add/remove)
// ---------------------------------------------------------------------------

function MembersPanel({ groupId, members }: { groupId: string; members?: Member[] }) {
  const t = useT();
  const [addOpen, setAddOpen] = useState(false);
  const [q, setQ] = useState('');
  const [selectedId, setSelectedId] = useState<string | number | undefined>();
  const [removeTarget, setRemoveTarget] = useState<Member | null>(null);
  const qc = useQueryClient();

  const peopleQuery = useQuery(peopleSearchQuery(q));
  const options: UserPickerOption[] = (peopleQuery.data ?? []).map(p => ({
    id: p.id,
    label: p.display_name,
    sub: p.external_id ?? undefined,
  }));

  const addMutation = useMutation({
    mutationFn: () => {
      const person = peopleQuery.data?.find(p => p.id === selectedId);
      if (!person) throw new Error('no person selected');
      return addMember(groupId, {
        display_name: person.display_name,
        external_id: person.external_id ?? undefined,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries(membersQuery(groupId));
      toast.success(t('grp.member.added'));
      setAddOpen(false);
      setSelectedId(undefined);
      setQ('');
    },
    onError: () => toast.error(t('grp.member.addError')),
  });

  const removeMutation = useMutation({
    mutationFn: (mid: number) => removeMember(groupId, mid),
    onSuccess: () => {
      qc.invalidateQueries(membersQuery(groupId));
      toast.success(t('grp.member.removed'));
      setRemoveTarget(null);
    },
    onError: () => toast.error(t('grp.member.removeError')),
  });

  return (
    <>
      <Card
        title={t('grp.member.title', { n: members?.length ?? 0 })}
        action={
          <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => setAddOpen(true)}>
            <UserPlus className="h-3.5 w-3.5" />
          </Button>
        }
      >
        {(members?.length ?? 0) === 0 && (
          <p className="text-xs text-muted-foreground">{t('grp.member.empty')}</p>
        )}
        {members?.map((m, i) => (
          <div key={m.id} className={`flex items-center gap-2.5 py-1.5 ${i > 0 ? 'border-t border-border' : ''}`}>
            <div className="h-[26px] w-[26px] rounded-full bg-gradient-to-br from-[hsl(168_60%_40%)] to-[hsl(220_50%_35%)] text-white text-[10.5px] font-medium tracking-tight grid place-items-center shrink-0">
              {(m.name[0] || '?').toUpperCase()}
            </div>
            <div className="text-[12.5px] flex-1 min-w-0">
              {m.name} {m.role && <span className="text-[11px] text-[hsl(var(--dim))]">· {m.role}</span>}
            </div>
            <div className="flex items-center gap-1">
              <StatusDot status={m.last_seen_at ? 'ok' : 'idle'} />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100">
                    <MoreHorizontal className="h-3.5 w-3.5" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    className="text-destructive focus:text-destructive"
                    onClick={() => setRemoveTarget(m)}
                  >
                    {t('grp.member.removeFromGroup')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        ))}
      </Card>

      {/* Add member dialog */}
      <Dialog open={addOpen} onOpenChange={v => { setAddOpen(v); if (!v) { setSelectedId(undefined); setQ(''); } }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('grp.member.addTitle')}</DialogTitle>
          </DialogHeader>
          <div className="mt-2">
            <UserPicker
              options={options}
              value={selectedId}
              onChange={id => setSelectedId(id)}
              onSearchChange={setQ}
              placeholder={t('grp.member.searchPlaceholder')}
            />
            <p className="text-xs text-muted-foreground mt-1.5">
              {t('grp.member.searchHint')}
            </p>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="ghost" onClick={() => setAddOpen(false)}>{t('common.cancel')}</Button>
            <Button
              disabled={!selectedId || addMutation.isPending}
              onClick={() => addMutation.mutate()}
            >
              {addMutation.isPending ? t('grp.member.adding') : t('grp.member.add')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Remove confirm dialog */}
      <Dialog open={!!removeTarget} onOpenChange={v => { if (!v) setRemoveTarget(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('grp.member.removeTitle')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {t('grp.member.removeQPre')}<strong>{removeTarget?.name}</strong>{t('grp.member.removeQPost')}
          </p>
          <DialogFooter className="mt-4">
            <Button variant="ghost" onClick={() => setRemoveTarget(null)}>{t('common.cancel')}</Button>
            <Button
              variant="destructive"
              disabled={removeMutation.isPending}
              onClick={() => removeTarget && removeMutation.mutate(removeTarget.id)}
            >
              {removeMutation.isPending ? t('common.deleting') : t('common.delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ---------------------------------------------------------------------------
// RightPanel
// ---------------------------------------------------------------------------

export function RightPanel({
  groupId,
  stats,
  members,
  files,
}: {
  groupId?: string;
  stats?: Stats;
  members?: Member[];
  files?: FileItem[];
}) {
  const t = useT();
  return (
    <aside className="flex flex-col gap-4 sticky top-[90px] self-start">
      <Card title={t('grp.panel.last7days')}>
        <div className="grid grid-cols-2 gap-3">
          <Stat label={t('grp.stats.messages')} value={stats?.messages} />
          <Stat label={t('grp.stats.tasks')} value={stats?.tasks} />
          <Stat label={t('grp.stats.reminders')} value={stats?.reminders} />
          <Stat label={t('grp.stats.decisions')} value={stats?.decisions} />
        </div>
      </Card>

      {groupId ? (
        <MembersPanel groupId={groupId} members={members} />
      ) : (
        <Card title={t('grp.member.title', { n: members?.length ?? 0 })}>
          {(members?.length ?? 0) === 0 && (
            <p className="text-xs text-muted-foreground">{t('grp.member.empty')}</p>
          )}
          {members?.map((m, i) => (
            <div key={m.id} className={`flex items-center gap-2.5 py-1.5 ${i > 0 ? 'border-t border-border' : ''}`}>
              <div className="h-[26px] w-[26px] rounded-full bg-gradient-to-br from-[hsl(168_60%_40%)] to-[hsl(220_50%_35%)] text-white text-[10.5px] font-medium tracking-tight grid place-items-center shrink-0">
                {(m.name[0] || '?').toUpperCase()}
              </div>
              <div className="text-[12.5px] flex-1 min-w-0">
                {m.name} {m.role && <span className="text-[11px] text-[hsl(var(--dim))]">· {m.role}</span>}
              </div>
              <StatusDot status={m.last_seen_at ? 'ok' : 'idle'} />
            </div>
          ))}
        </Card>
      )}

      <Card title={t('grp.panel.recentFiles')}>
        <div className="flex flex-col gap-2.5 text-[13px]">
          {(files?.length ?? 0) === 0 && <p className="text-xs text-muted-foreground">{t('grp.panel.noFiles')}</p>}
          {files?.map(f => {
            const Icon = f.kind === 'image' ? ImageIcon : f.kind === 'link' ? LinkIcon : FileText;
            return (
              <div key={f.id} className="flex items-center gap-2 min-w-0">
                <Icon className="h-3.5 w-3.5 shrink-0 text-[hsl(var(--info))]" strokeWidth={2} />
                <span className="truncate">{f.name}</span>
                <span className="text-[11px] text-[hsl(var(--dim))] ml-auto shrink-0">{relativeTime(f.created_at)}</span>
              </div>
            );
          })}
        </div>
      </Card>
    </aside>
  );
}

function Card({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-[10px] bg-card p-4 shadow-[0_0_0_1px_hsl(var(--border-strong)),0_1px_2px_rgba(0,0,0,.04)]">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[11px] uppercase tracking-wider text-[hsl(var(--dim))] font-medium">{title}</h3>
        {action}
      </div>
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div>
      <p className="text-xl font-semibold tracking-tight leading-tight">{value !== undefined ? formatNumber(value) : '—'}</p>
      <p className="text-[11px] text-muted-foreground mt-0.5">{label}</p>
    </div>
  );
}
