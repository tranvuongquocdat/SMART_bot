import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { useT } from '@/lib/i18n';
import { accountQuery, patchAccount } from './api';

export default function AccountTab() {
  const t = useT();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery(accountQuery);

  const [name, setName] = useState('');

  useEffect(() => {
    if (data) {
      setName(data.name ?? '');
    }
  }, [data]);

  const mut = useMutation({
    mutationFn: () => patchAccount({ name: name || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: accountQuery.queryKey });
      toast.success(t('settings.account.savedName'));
    },
    onError: () => toast.error(t('common.saveError')),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">{t('common.loading')}</p>;
  if (!data) return null;

  return (
    <div className="space-y-6 max-w-lg">
      {/* Read-only info */}
      <div className="rounded-lg border bg-card p-4 space-y-2 text-sm">
        <div className="flex gap-2">
          <span className="text-muted-foreground w-36">{t('settings.account.email')}</span>
          <span className="font-medium">{data.email}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-muted-foreground w-36">{t('settings.account.role')}</span>
          <span className="font-medium capitalize">{data.role}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-muted-foreground w-36">{t('settings.account.google')}</span>
          <span className="font-medium">
            {data.google_linked
              ? t('settings.account.googleLinked')
              : t('settings.account.googleUnlinked')}
          </span>
        </div>
        <div className="flex gap-2">
          <span className="text-muted-foreground w-36">{t('settings.account.plan')}</span>
          <span className="font-medium">
            {data.subscription_status ?? '—'}
            {data.subscription_expiry && (
              <span className="text-muted-foreground ml-1">
                {t('settings.account.planExpiry', {
                  date: new Date(data.subscription_expiry).toLocaleDateString(),
                })}
              </span>
            )}
          </span>
        </div>
        <div className="flex gap-2">
          <span className="text-muted-foreground w-36">{t('settings.account.costCap')}</span>
          <span className="font-medium">${data.cost_cap_usd_daily.toFixed(2)}</span>
        </div>
      </div>

      {/* Editable: display name */}
      <div className="space-y-2">
        <Label htmlFor="acc-name">{t('settings.account.displayName')}</Label>
        <Input
          id="acc-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('settings.account.displayNamePlaceholder')}
        />
      </div>

      <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
        {mut.isPending ? t('common.saving') : t('common.save')}
      </Button>
    </div>
  );
}
