import { useEffect, useState } from 'react';
import { useSuspenseQuery, useQueryClient, queryOptions } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { api, errorMessage } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';

type PlatformSettings = {
  history_window_dm: number;
  history_window_group: number;
  raw_message_retention_days: number;
};

const platformQuery = queryOptions({
  queryKey: ['superadmin', 'platform-settings'],
  queryFn: () => api<PlatformSettings>('/api/v1/superadmin/platform-settings'),
});

const FIELDS: { key: keyof PlatformSettings; label: string; hint: string; max: number }[] = [
  { key: 'history_window_dm', label: 'platform.historyDm', hint: 'platform.historyDmHint', max: 50 },
  { key: 'history_window_group', label: 'platform.historyGroup', hint: 'platform.historyGroupHint', max: 50 },
  { key: 'raw_message_retention_days', label: 'platform.retention', hint: 'platform.retentionHint', max: 3650 },
];

export default function PlatformPage() {
  const t = useT();
  const qc = useQueryClient();
  const { data } = useSuspenseQuery(platformQuery);
  const [form, setForm] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm(Object.fromEntries(FIELDS.map((f) => [f.key, String(data[f.key])])));
  }, [data]);

  async function save() {
    setSaving(true);
    try {
      const body = Object.fromEntries(
        FIELDS.filter((f) => form[f.key] !== '').map((f) => [f.key, Number(form[f.key])])
      );
      await api('/api/v1/superadmin/platform-settings', {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
      toast.success(t('common.saved'));
      await qc.invalidateQueries({ queryKey: platformQuery.queryKey });
    } catch (e) {
      toast.error(errorMessage(e, t('common.saveError')));
    } finally {
      setSaving(false);
    }
  }

  return (
    <PageWrap>
      <PageHeader title={t('platform.title')} subtitle={t('platform.subtitle')} />
      <PageSection>
        <div className="max-w-md space-y-4">
          {FIELDS.map((f) => (
            <div key={f.key} className="space-y-1.5">
              <Label htmlFor={`pf-${f.key}`}>{t(f.label)}</Label>
              <Input
                id={`pf-${f.key}`}
                type="number"
                min={0}
                max={f.max}
                value={form[f.key] ?? ''}
                onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
              />
              <p className="text-xs text-muted-foreground">{t(f.hint)}</p>
            </div>
          ))}
          <Button onClick={save} disabled={saving}>
            {saving ? t('common.saving') : t('common.save')}
          </Button>
        </div>
      </PageSection>
    </PageWrap>
  );
}
