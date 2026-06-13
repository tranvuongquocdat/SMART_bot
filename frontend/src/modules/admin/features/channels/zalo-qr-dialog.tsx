import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Loader2, RefreshCw, Smartphone } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ApiError } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { startZaloQrLogin, zaloQrLoginStatus, type ZaloQrStatus } from './api';

const POLL_MS = 1500;

const fmtCountdown = (s: number) =>
  `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

export function ZaloQrDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const [state, setState] = useState<ZaloQrStatus | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState<number | null>(null);
  const loginIdRef = useRef<string | null>(null);
  const stoppedRef = useRef(false);

  // Đếm ngược mượt 1s giữa các lần poll (poll đồng bộ lại từ server)
  useEffect(() => {
    if (countdown == null || countdown <= 0) return;
    const timer = setTimeout(() => setCountdown((c) => (c == null ? null : c - 1)), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  async function begin() {
    setState(null);
    setStartError(null);
    try {
      const { login_id } = await startZaloQrLogin();
      loginIdRef.current = login_id;
    } catch (e) {
      const detail =
        e instanceof ApiError && typeof (e.body as { detail?: string })?.detail === 'string'
          ? (e.body as { detail: string }).detail
          : t('zaloqr.startError');
      setStartError(detail);
    }
  }

  // Mở dialog → mở phiên login + poll trạng thái tới khi success/error
  useEffect(() => {
    if (!open) return;
    stoppedRef.current = false;
    begin();
    const timer = setInterval(async () => {
      const id = loginIdRef.current;
      if (!id || stoppedRef.current) return;
      try {
        const s = await zaloQrLoginStatus(id);
        if (stoppedRef.current) return;
        setState(s);
        setCountdown(s.status === 'qr' || s.status === 'scanned' ? s.expires_in_s : null);
        if (s.status === 'success') {
          stoppedRef.current = true;
          toast.success(
            t('zaloqr.connected', { name: s.display_name ? ` — ${s.display_name}` : '' })
          );
          qc.invalidateQueries({ queryKey: ['admin', 'channels'] });
          onClose();
        } else if (s.status === 'error') {
          stoppedRef.current = true;
        }
      } catch {
        // phiên hết hạn server-side → dừng poll, cho retry
        stoppedRef.current = true;
        setState({
          status: 'error',
          qr_image_b64: null,
          display_name: null,
          error: t('zaloqr.expired'),
          bot_account_id: null,
          expires_in_s: 0,
        });
      }
    }, POLL_MS);
    return () => {
      stoppedRef.current = true;
      clearInterval(timer);
      loginIdRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const status = state?.status;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t('zaloqr.title')}</DialogTitle>
          <DialogDescription>
            {t('zaloqr.descPre')}<strong>{t('zaloqr.descBold')}</strong>{t('zaloqr.descPost')}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col items-center gap-3 py-2 min-h-[280px] justify-center">
          {startError ? (
            <>
              <p className="text-sm text-destructive text-center">{startError}</p>
              <Button size="sm" variant="outline" onClick={begin}>
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                {t('zaloqr.retry')}
              </Button>
            </>
          ) : status === 'qr' && state?.qr_image_b64 ? (
            <>
              <img
                src={`data:image/png;base64,${state.qr_image_b64}`}
                alt={t('zaloqr.qrAlt')}
                className="h-56 w-56 rounded-lg border bg-white p-2"
              />
              <p className="text-xs text-muted-foreground">
                {t('zaloqr.autoRefresh')}
                {countdown != null && (
                  <>
                    {' '}{t('zaloqr.sessionLeft')}{' '}
                    <span className="font-mono font-medium text-foreground tabular-nums">
                      {fmtCountdown(countdown)}
                    </span>
                  </>
                )}
              </p>
            </>
          ) : status === 'scanned' ? (
            <>
              <Smartphone className="h-10 w-10 text-primary" />
              <p className="text-sm text-center">
                {t('zaloqr.scanned', { by: state?.display_name ? t('zaloqr.by', { name: state.display_name }) : '' })}
              </p>
            </>
          ) : status === 'error' ? (
            <>
              <p className="text-sm text-destructive text-center">
                {state?.error ?? t('zaloqr.loginFailed')}
              </p>
              <Button size="sm" variant="outline" onClick={begin}>
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                {t('zaloqr.retry')}
              </Button>
            </>
          ) : (
            <>
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              <p className="text-sm text-muted-foreground">{t('zaloqr.creating')}</p>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
