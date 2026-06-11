import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { marked } from 'marked';
import {
  Check, FileText, History, Link2, Maximize2, Pencil,
  RefreshCw, Users, X,
} from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { relativeTime } from '@/lib/format';
import { TimelineCard } from './timeline-card';
import { patchActionItem } from '../action-items/api';
import {
  groupQuery, itemsQuery, timelineQuery, statsQuery, membersQuery, filesQuery,
  noteQuery, noteVersionsQuery, noteTemplatesQuery,
  patchNote, refreshNote, restoreNoteVersion, setGroupTemplate,
} from './api';
import type { Item } from './api';

const MIN_W = 420;
const DEFAULT_W = 620;

function ChannelChip({ channel }: { channel: string }) {
  if (channel === 'zalo') return <Badge variant="zalo">{channel}</Badge>;
  if (channel === 'telegram') return <Badge variant="telegram">{channel}</Badge>;
  return <Badge variant="secondary">{channel}</Badge>;
}

const TABS = [
  { key: 'note', label: 'Note' },
  { key: 'timeline', label: 'Thời gian' },
  { key: 'tasks', label: 'Tác vụ' },
  { key: 'decisions', label: 'Quyết định' },
  { key: 'members', label: 'Thành viên' },
  { key: 'files', label: 'Tệp & link' },
] as const;
type TabKey = (typeof TABS)[number]['key'];

// ---------------------------------------------------------------- Note tab

function NoteTab({ id }: { id: string }) {
  const qc = useQueryClient();
  const note = useQuery(noteQuery(id));
  const versions = useQuery(noteVersionsQuery(id));
  const templates = useQuery(noteTemplatesQuery());
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['admin', 'group', id, 'note'] });
    qc.invalidateQueries({ queryKey: ['admin', 'group', id, 'note-versions'] });
  };

  const saveMut = useMutation({
    mutationFn: () => patchNote(id, draft),
    onSuccess: () => {
      setEditing(false);
      invalidate();
      toast.success('Đã lưu note');
    },
    onError: () => toast.error('Lưu note thất bại'),
  });

  const refreshMut = useMutation({
    mutationFn: () => refreshNote(id),
    onSuccess: () => {
      toast.success('Bot đang cập nhật note — sẽ hiện trong giây lát');
      setTimeout(invalidate, 6000);
    },
    onError: () => toast.error('Không gửi được yêu cầu cập nhật'),
  });

  const restoreMut = useMutation({
    mutationFn: (vid: number) => restoreNoteVersion(id, vid),
    onSuccess: () => {
      invalidate();
      toast.success('Đã khôi phục phiên bản');
    },
    onError: () => toast.error('Khôi phục thất bại'),
  });

  const templateMut = useMutation({
    mutationFn: (tid: number | null) => setGroupTemplate(id, tid),
    onSuccess: () => {
      invalidate();
      toast.success('Đã đổi template — note sẽ theo cấu trúc mới ở lần cập nhật tới');
    },
    onError: () => toast.error('Đổi template thất bại'),
  });

  if (note.isLoading) return <Skeleton className="h-40 w-full" />;
  if (!note.data) return null;

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        {!editing ? (
          <>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setDraft(note.data!.content);
                setEditing(true);
              }}
            >
              <Pencil className="h-3.5 w-3.5 mr-1.5" />
              Sửa
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={refreshMut.isPending}
              onClick={() => refreshMut.mutate()}
            >
              <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${refreshMut.isPending ? 'animate-spin' : ''}`} />
              Cập nhật ngay
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="outline">
                  <History className="h-3.5 w-3.5 mr-1.5" />
                  Lịch sử
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="max-h-72 overflow-y-auto">
                {(versions.data ?? []).length === 0 && (
                  <DropdownMenuItem disabled>Chưa có phiên bản nào</DropdownMenuItem>
                )}
                {(versions.data ?? []).map((v) => (
                  <DropdownMenuItem key={v.id} onClick={() => restoreMut.mutate(v.id)}>
                    <span className="font-mono text-xs mr-2">#{v.id}</span>
                    {relativeTime(v.emitted_at)} · {v.emitted_by}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <div className="ml-auto w-44">
              <Select
                value={note.data.template_id?.toString() ?? 'none'}
                onValueChange={(v) =>
                  templateMut.mutate(v === 'none' ? null : parseInt(v, 10))
                }
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="Template" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">— template mặc định —</SelectItem>
                  {(templates.data ?? []).map((t) => (
                    <SelectItem key={t.id} value={t.id.toString()}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </>
        ) : (
          <>
            <Button size="sm" disabled={saveMut.isPending} onClick={() => saveMut.mutate()}>
              <Check className="h-3.5 w-3.5 mr-1.5" />
              {saveMut.isPending ? 'Đang lưu…' : 'Lưu'}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
              Huỷ
            </Button>
          </>
        )}
      </div>

      {note.data.updated_at && !editing && (
        <p className="text-[11px] text-muted-foreground">
          Bot cập nhật {relativeTime(note.data.updated_at)}
        </p>
      )}

      {/* Content */}
      {editing ? (
        <textarea
          className="w-full min-h-[420px] rounded-lg border bg-card p-4 text-sm font-mono leading-relaxed focus:outline-none focus:ring-1 focus:ring-ring"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
      ) : note.data.content ? (
        <div
          className="prose-note rounded-lg border bg-card p-5 text-sm leading-[1.75] [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:text-base [&_h2]:font-semibold [&_h3]:text-sm [&_h3]:font-semibold [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-2 [&_li]:my-0.5 [&_hr]:my-4 [&_code]:text-xs [&_code]:bg-muted [&_code]:px-1 [&_code]:rounded"
          dangerouslySetInnerHTML={{ __html: marked.parse(note.data.content) as string }}
        />
      ) : (
        <div className="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground">
          <FileText className="h-6 w-6 mx-auto mb-2 opacity-50" />
          Chưa có note. Bot sẽ tự tạo khi nhóm có tin nhắn, hoặc bấm "Cập nhật ngay".
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------- Items tabs

function TaskRow({ item, groupId }: { item: Item; groupId: string }) {
  const qc = useQueryClient();
  const mut = useMutation({
    mutationFn: () => patchActionItem(item.id, { done: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'group', groupId, 'items'] });
      toast.success('Đã đánh dấu xong');
    },
    onError: () => toast.error('Thao tác thất bại'),
  });
  return (
    <div className="flex items-start gap-2.5 py-2.5 px-3.5 bg-card rounded-lg border">
      <button
        className="h-4 w-4 rounded border-[1.5px] border-[hsl(var(--border-strong))] mt-0.5 shrink-0 hover:bg-primary/20 transition-colors"
        onClick={() => mut.mutate()}
        disabled={mut.isPending}
        aria-label="Đánh dấu xong"
      />
      <div className="flex-1 min-w-0">
        <p className="text-[13.5px]">{item.text}</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {item.assignee ?? 'Chưa giao'}
          {item.due_at && ` · hạn ${relativeTime(item.due_at)}`}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Panel

export function GroupPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const navigate = useNavigate();
  const group = useQuery(groupQuery(id));
  const items = useQuery(itemsQuery(id));
  const timeline = useQuery(timelineQuery(id));
  const stats = useQuery(statsQuery(id));
  const members = useQuery(membersQuery(id));
  const files = useQuery(filesQuery(id));

  const [tab, setTab] = useState<TabKey>('note');
  const [width, setWidth] = useState(() => {
    const saved = localStorage.getItem('group-panel-w');
    return saved ? parseInt(saved, 10) : DEFAULT_W;
  });
  const dragging = useRef(false);

  const onDrag = useCallback((e: MouseEvent) => {
    if (!dragging.current) return;
    const w = Math.min(Math.max(window.innerWidth - e.clientX, MIN_W), window.innerWidth - 240);
    setWidth(w);
  }, []);

  useEffect(() => {
    const stop = () => {
      if (dragging.current) {
        dragging.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        setWidth((w) => {
          localStorage.setItem('group-panel-w', String(w));
          return w;
        });
      }
    };
    window.addEventListener('mousemove', onDrag);
    window.addEventListener('mouseup', stop);
    return () => {
      window.removeEventListener('mousemove', onDrag);
      window.removeEventListener('mouseup', stop);
    };
  }, [onDrag]);

  const tasks = (items.data ?? []).filter((i) => i.type === 'task');
  const decisions = (items.data ?? []).filter((i) => i.type === 'decision');

  return (
    <>
      {/* Lớp mờ nhẹ phía sau, bấm ra ngoài để đóng */}
      <div className="fixed inset-0 z-30 bg-black/10" onClick={onClose} />

      <aside
        className="fixed inset-y-0 right-0 z-40 bg-background border-l shadow-2xl flex flex-col"
        style={{ width }}
      >
        {/* Drag handle */}
        <div
          className="absolute inset-y-0 left-0 w-1.5 cursor-col-resize hover:bg-primary/30 transition-colors"
          onMouseDown={() => {
            dragging.current = true;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
          }}
        />

        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b shrink-0">
          {group.isLoading ? (
            <Skeleton className="h-5 w-40" />
          ) : (
            <>
              <p className="font-semibold truncate">{group.data?.name}</p>
              {group.data && <ChannelChip channel={group.data.channel} />}
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Users className="h-3.5 w-3.5" />
                {group.data?.members_count ?? 0}
              </span>
            </>
          )}
          <div className="ml-auto flex items-center gap-0.5">
            <button
              className="text-muted-foreground hover:text-foreground transition-colors p-1.5"
              onClick={() => navigate(`/app/admin/groups/${id}`)}
              aria-label="Mở toàn màn hình"
              title="Mở toàn màn hình"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
            <button
              className="text-muted-foreground hover:text-foreground transition-colors p-1.5"
              onClick={onClose}
              aria-label="Đóng panel"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-5 pt-3 border-b shrink-0 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-3 py-2 text-[13px] whitespace-nowrap border-b-2 -mb-px transition-colors ${
                tab === t.key
                  ? 'border-primary text-foreground font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {t.label}
              {t.key === 'tasks' && tasks.length > 0 && ` (${tasks.length})`}
              {t.key === 'decisions' && decisions.length > 0 && ` (${decisions.length})`}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 min-h-0">
          {tab === 'note' && <NoteTab id={id} />}

          {tab === 'timeline' && (
            <div className="space-y-4">
              {stats.data && (
                <div className="grid grid-cols-4 divide-x rounded-lg border text-center">
                  {[
                    { label: 'Tin nhắn', value: stats.data.messages },
                    { label: 'Tác vụ', value: stats.data.tasks },
                    { label: 'Nhắc lịch', value: stats.data.reminders },
                    { label: 'Quyết định', value: stats.data.decisions },
                  ].map((s) => (
                    <div key={s.label} className="py-2">
                      <p className="text-sm font-semibold tabular-nums">{s.value}</p>
                      <p className="text-[10px] text-muted-foreground">{s.label}</p>
                    </div>
                  ))}
                </div>
              )}
              {timeline.data && <TimelineCard messages={timeline.data.messages} />}
            </div>
          )}

          {tab === 'tasks' &&
            (tasks.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-10">
                Hôm nay chưa có tác vụ nào được trích xuất.
              </p>
            ) : (
              <div className="space-y-2">
                {tasks.map((t) => (
                  <TaskRow key={t.id} item={t} groupId={id} />
                ))}
              </div>
            ))}

          {tab === 'decisions' &&
            (decisions.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-10">
                Chưa có quyết định nào được ghi nhận hôm nay.
              </p>
            ) : (
              <div className="space-y-2">
                {decisions.map((d) => (
                  <div key={d.id} className="py-2.5 px-3.5 bg-card rounded-lg border">
                    <p className="text-[13.5px]">{d.text}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {new Date(d.created_at).toLocaleString('vi-VN')}
                    </p>
                  </div>
                ))}
              </div>
            ))}

          {tab === 'members' &&
            ((members.data ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-10">
                Chưa ghi nhận thành viên nào.
              </p>
            ) : (
              <div className="divide-y rounded-lg border">
                {(members.data ?? []).map((m) => (
                  <div key={m.id} className="flex items-center gap-3 px-4 py-2.5">
                    <div className="h-7 w-7 rounded-full bg-primary/15 text-primary text-xs font-semibold flex items-center justify-center shrink-0">
                      {(m.name || '?').charAt(0).toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{m.name}</p>
                      <p className="text-xs text-muted-foreground">{m.role}</p>
                    </div>
                    {m.last_seen_at && (
                      <span className="text-[11px] text-muted-foreground shrink-0">
                        {relativeTime(m.last_seen_at)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ))}

          {tab === 'files' &&
            ((files.data ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-10">
                Chưa có tệp hoặc link nào được chia sẻ trong nhóm.
              </p>
            ) : (
              <div className="divide-y rounded-lg border">
                {(files.data ?? []).map((f) => (
                  <a
                    key={f.id}
                    href={f.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/40 transition-colors"
                  >
                    {f.kind === 'link' ? (
                      <Link2 className="h-4 w-4 text-muted-foreground shrink-0" />
                    ) : (
                      <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm truncate">{f.name}</p>
                      <p className="text-[11px] text-muted-foreground">
                        {f.kind} · {relativeTime(f.created_at)}
                      </p>
                    </div>
                  </a>
                ))}
              </div>
            ))}
        </div>
      </aside>
    </>
  );
}
