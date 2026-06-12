import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Megaphone } from 'lucide-react';
import { toast } from 'sonner';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/empty-state';
import { errorMessage } from '@/lib/api';
import { relativeTime } from '@/lib/format';
import { announcementsQuery, createAnnouncement } from './api';

export default function AnnouncementsPage() {
  const qc = useQueryClient();
  const list = useQuery(announcementsQuery);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [link, setLink] = useState('');

  const mut = useMutation({
    mutationFn: () =>
      createAnnouncement({ title: title.trim(), body: body.trim(), link: link.trim() }),
    onSuccess: () => {
      toast.success('Đã gửi thông báo tới mọi người dùng');
      setTitle('');
      setBody('');
      setLink('');
      qc.invalidateQueries({ queryKey: ['superadmin', 'announcements'] });
    },
    onError: (e) => toast.error(errorMessage(e, 'Gửi thông báo thất bại')),
  });

  return (
    <PageWrap className="max-w-[760px]">
      <PageHeader
        title="Thông báo"
        subtitle="Gửi thông báo broadcast tới tất cả người dùng — vd phiên bản mới, bảo trì, sự kiện quan trọng."
      />

      <PageSection>
        <div className="rounded-xl border bg-card p-4 space-y-3">
          <div className="space-y-1.5">
            <Label>Tiêu đề</Label>
            <Input
              placeholder="VD: Đã ra mắt phiên bản 2.1"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Nội dung</Label>
            <Textarea
              rows={3}
              placeholder="Mô tả ngắn gọn nội dung thông báo…"
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>
              Link <span className="text-xs text-muted-foreground">(tuỳ chọn)</span>
            </Label>
            <Input
              placeholder="/app/admin/dashboard hoặc https://…"
              value={link}
              onChange={(e) => setLink(e.target.value)}
            />
          </div>
          <Button disabled={!title.trim() || mut.isPending} onClick={() => mut.mutate()}>
            <Megaphone className="h-3.5 w-3.5 mr-1.5" />
            {mut.isPending ? 'Đang gửi…' : 'Gửi cho tất cả'}
          </Button>
        </div>
      </PageSection>

      <PageSection>
        <h2 className="text-sm font-semibold mb-3">Đã gửi gần đây</h2>
        {list.isLoading ? (
          <Skeleton className="h-[160px] rounded-[12px]" />
        ) : (list.data ?? []).length === 0 ? (
          <EmptyState icon={Megaphone} title="Chưa gửi thông báo nào" />
        ) : (
          <div className="divide-y divide-border rounded-xl border">
            {(list.data ?? []).map((a) => (
              <div key={a.id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium truncate">{a.title}</p>
                  <span className="text-[11px] text-muted-foreground shrink-0">
                    {relativeTime(a.created_at)}
                  </span>
                </div>
                {a.body && <p className="text-xs text-muted-foreground mt-0.5">{a.body}</p>}
                {a.link && (
                  <p className="text-[11px] text-[hsl(var(--primary))] mt-0.5 truncate">{a.link}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </PageSection>
    </PageWrap>
  );
}
