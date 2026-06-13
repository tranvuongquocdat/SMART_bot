import { useState, useEffect, type ChangeEvent } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Save, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { useT } from '@/lib/i18n';
import { promptDetailQuery, createPrompt, patchPrompt } from './api';

export default function PromptDetailPage() {
  const t = useT();
  const { id } = useParams<{ id: string }>();
  const promptId = Number(id);
  const qc = useQueryClient();

  const detail = useQuery(promptDetailQuery(promptId));

  const [body, setBody] = useState('');
  const [notes, setNotes] = useState('');
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (detail.data) {
      setBody(detail.data.body);
      setNotes(detail.data.notes ?? '');
      setDirty(false);
    }
  }, [detail.data]);

  // Create a new version (same key, auto-incremented version)
  const saveMut = useMutation({
    mutationFn: () =>
      createPrompt({
        key: detail.data!.key,
        body,
        notes: notes.trim() || null,
      }),
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'prompts'] });
      toast.success(t('sa.prompt.savedVersion', { id: data.id }));
      setDirty(false);
    },
    onError: () => toast.error(t('sa.common.saveError')),
  });

  const activateMut = useMutation({
    mutationFn: () => patchPrompt(promptId, { is_active: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'prompts', promptId] });
      qc.invalidateQueries({ queryKey: ['superadmin', 'prompts'] });
      toast.success(t('sa.prompt.activatedShort'));
    },
    onError: () => toast.error(t('sa.prompt.activateError')),
  });

  if (detail.isLoading) {
    return (
      <PageWrap className="max-w-[860px]">
        <Skeleton className="h-[400px] rounded-[12px]" />
      </PageWrap>
    );
  }

  if (!detail.data) {
    return (
      <PageWrap className="max-w-[860px]">
        <p className="text-muted-foreground">{t('sa.prompt.notFound')}</p>
      </PageWrap>
    );
  }

  const row = detail.data;

  return (
    <PageWrap className="max-w-[860px]">
      <PageSection>
        <Link
          to="/app/superadmin/prompts"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {t('sa.prompt.backList')}
        </Link>
      </PageSection>

      <PageHeader
        title={`${row.key} · v${row.version}`}
        subtitle={row.notes ?? undefined}
        actions={
          row.is_active ? (
            <Badge variant="default">active</Badge>
          ) : (
            <Button
              size="sm"
              variant="outline"
              disabled={activateMut.isPending}
              onClick={() => activateMut.mutate()}
            >
              <Zap className="h-3 w-3 mr-1" />
              {t('sa.prompt.activate')}
            </Button>
          )
        }
      />

      <PageSection>
        <div className="grid gap-5">
          <div className="grid gap-1.5">
            <Label>Body</Label>
            <Textarea
              rows={16}
              className="font-mono text-xs resize-y"
              value={body}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => {
                setBody(e.target.value);
                setDirty(true);
              }}
            />
          </div>

          <div className="grid gap-1.5">
            <Label>{t('sa.prompt.notesNewVersion')}</Label>
            <Input
              placeholder={t('sa.prompt.notesPlaceholder')}
              value={notes}
              onChange={(e: ChangeEvent<HTMLInputElement>) => {
                setNotes(e.target.value);
                setDirty(true);
              }}
            />
          </div>

          <div className="flex justify-end">
            <Button
              disabled={saveMut.isPending || !dirty}
              onClick={() => saveMut.mutate()}
            >
              <Save className="h-3.5 w-3.5 mr-1.5" />
              {saveMut.isPending ? t('sa.common.saving') : t('sa.prompt.saveNewVersion')}
            </Button>
          </div>
        </div>
      </PageSection>
    </PageWrap>
  );
}
