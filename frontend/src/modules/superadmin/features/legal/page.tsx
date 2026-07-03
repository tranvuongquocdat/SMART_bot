import { useState } from 'react';
import { useSuspenseQuery, useQueryClient, queryOptions } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { api, errorMessage } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';

type LegalDoc = {
  id: number;
  kind: 'terms' | 'privacy';
  version: number;
  content_md: string;
  published_at: string;
  is_active: boolean;
  acceptances: number;
};

const legalQuery = queryOptions({
  queryKey: ['superadmin', 'legal'],
  queryFn: () => api<LegalDoc[]>('/api/v1/superadmin/legal'),
});

function DocEditor({ kind, docs }: { kind: 'terms' | 'privacy'; docs: LegalDoc[] }) {
  const t = useT();
  const qc = useQueryClient();
  const active = docs.find((d) => d.kind === kind && d.is_active) ?? null;
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const value = draft ?? active?.content_md ?? '';

  async function publish() {
    setSaving(true);
    try {
      await api(`/api/v1/superadmin/legal/${kind}`, {
        method: 'POST',
        body: JSON.stringify({ content_md: value }),
      });
      toast.success(t('legalAdmin.published'));
      setDraft(null);
      await qc.invalidateQueries({ queryKey: ['superadmin', 'legal'] });
    } catch (e) {
      toast.error(errorMessage(e, t('legalAdmin.publishError')));
    } finally {
      setSaving(false);
    }
  }

  return (
    <PageSection>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold">
          {kind === 'terms' ? t('legal.terms') : t('legal.privacy')}
        </h2>
        <div className="flex items-center gap-3">
          {active && (
            <span className="text-xs text-muted-foreground">
              {t('legalAdmin.activeVersion', { v: active.version, n: active.acceptances })}
            </span>
          )}
          <a
            href={`/app/legal/${kind}`}
            target="_blank"
            rel="noreferrer"
            className="text-xs underline underline-offset-4 text-muted-foreground hover:text-foreground"
          >
            {t('legalAdmin.viewPublic')}
          </a>
        </div>
      </div>
      <div className="flex flex-col gap-3">
        {!active && <Badge variant="outline">{t('legalAdmin.notPublished')}</Badge>}
        <Textarea
          value={value}
          onChange={(e) => setDraft(e.target.value)}
          rows={14}
          className="font-mono text-xs leading-5"
          placeholder={t('legalAdmin.placeholder')}
        />
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={publish}
            disabled={saving || !value.trim() || draft === null}
          >
            {saving ? '…' : t('legalAdmin.publish')}
          </Button>
        </div>
      </div>
    </PageSection>
  );
}

export default function LegalAdminPage() {
  const t = useT();
  const { data: docs } = useSuspenseQuery(legalQuery);
  return (
    <PageWrap>
      <PageHeader title={t('legalAdmin.title')} subtitle={t('legalAdmin.subtitle')} />
      <DocEditor kind="terms" docs={docs} />
      <DocEditor kind="privacy" docs={docs} />
    </PageWrap>
  );
}
