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
import { useT } from '@/lib/i18n';
import { announcementsQuery, createAnnouncement } from './api';

export default function AnnouncementsPage() {
  const t = useT();
  const qc = useQueryClient();
  const list = useQuery(announcementsQuery);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [link, setLink] = useState('');

  const mut = useMutation({
    mutationFn: () =>
      createAnnouncement({ title: title.trim(), body: body.trim(), link: link.trim() }),
    onSuccess: () => {
      toast.success(t('sa.ann.sent'));
      setTitle('');
      setBody('');
      setLink('');
      qc.invalidateQueries({ queryKey: ['superadmin', 'announcements'] });
    },
    onError: (e) => toast.error(errorMessage(e, t('sa.ann.sendError'))),
  });

  return (
    <PageWrap className="max-w-[760px]">
      <PageHeader
        title={t('nav.sa.announcements')}
        subtitle={t('sa.ann.subtitle')}
      />

      <PageSection>
        <div className="rounded-xl border bg-card p-4 space-y-3">
          <div className="space-y-1.5">
            <Label>{t('sa.ann.title')}</Label>
            <Input
              placeholder={t('sa.ann.titlePlaceholder')}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t('sa.ann.body')}</Label>
            <Textarea
              rows={3}
              placeholder={t('sa.ann.bodyPlaceholder')}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>
              Link <span className="text-xs text-muted-foreground">{t('sa.ann.optional')}</span>
            </Label>
            <Input
              placeholder={t('sa.ann.linkPlaceholder')}
              value={link}
              onChange={(e) => setLink(e.target.value)}
            />
          </div>
          <Button disabled={!title.trim() || mut.isPending} onClick={() => mut.mutate()}>
            <Megaphone className="h-3.5 w-3.5 mr-1.5" />
            {mut.isPending ? t('sa.ann.sending') : t('sa.ann.sendAll')}
          </Button>
        </div>
      </PageSection>

      <PageSection>
        <h2 className="text-sm font-semibold mb-3">{t('sa.ann.recent')}</h2>
        {list.isLoading ? (
          <Skeleton className="h-[160px] rounded-[12px]" />
        ) : (list.data ?? []).length === 0 ? (
          <EmptyState icon={Megaphone} title={t('sa.ann.empty')} />
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
