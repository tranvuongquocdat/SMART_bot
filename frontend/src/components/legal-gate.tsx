import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { useT } from '@/lib/i18n';

type Status = { needs_acceptance: boolean; pending: { kind: string; version: number }[] };

/**
 * Cổng điều khoản (PDPL): sau đăng nhập, nếu có bản ToS/Privacy active mà user
 * chưa chấp nhận → modal chặn (không đóng được) tới khi bấm đồng ý.
 * Render trong layout admin + superadmin.
 */
export function LegalGate() {
  const t = useT();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const { data } = useQuery({
    queryKey: ['legal', 'acceptance-status'],
    queryFn: () => api<Status>('/api/v1/legal/acceptance-status'),
    staleTime: 5 * 60_000,
  });

  if (!data?.needs_acceptance) return null;

  async function accept() {
    setBusy(true);
    try {
      await api('/api/v1/legal/accept', { method: 'POST', body: JSON.stringify({}) });
      await qc.invalidateQueries({ queryKey: ['legal', 'acceptance-status'] });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open>
      <DialogContent
        className="max-w-md [&>button]:hidden"
        onInteractOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>{t('legal.gate.title')}</DialogTitle>
          <DialogDescription>{t('legal.gate.desc')}</DialogDescription>
        </DialogHeader>
        <div className="flex gap-4 text-sm">
          <a href="/app/legal/terms" target="_blank" rel="noreferrer" className="underline underline-offset-4">
            {t('legal.terms')}
          </a>
          <a href="/app/legal/privacy" target="_blank" rel="noreferrer" className="underline underline-offset-4">
            {t('legal.privacy')}
          </a>
        </div>
        <DialogFooter>
          <Button onClick={accept} disabled={busy}>
            {busy ? '…' : t('legal.gate.accept')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
