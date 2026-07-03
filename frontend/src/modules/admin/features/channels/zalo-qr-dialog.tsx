import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Loader2, RefreshCw, Smartphone } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ApiError } from '@/lib/api';
import { useT } from '@/lib/i18n';
import {
  mintLinkToken,
  startZaloQrLogin,
  zaloQrLoginStatus,
  type LinkToken,
  type ZaloQrStatus,
} from './api';

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
  // PDPL: lần đầu kết nối cần boss tick cam kết (409 consent_required từ BE).
  const [needConsent, setNeedConsent] = useState(false);
  const [consentChecked, setConsentChecked] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  // Sau khi QR success → bước handshake để bot nhận diện acc chính của boss.
  const [handshake, setHandshake] = useState<LinkToken | null>(null);
  const [handshakeError, setHandshakeError] = useState(false);
  const loginIdRef = useRef<string | null>(null);
  const stoppedRef = useRef(false);

  // Đếm ngược mượt 1s giữa các lần poll (poll đồng bộ lại từ server)
  useEffect(() => {
    if (countdown == null || countdown <= 0) return;
    const timer = setTimeout(() => setCountdown((c) => (c == null ? null : c - 1)), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  async function begin(consentConfirmed = false) {
    setState(null);
    setStartError(null);
    setNeedConsent(false);
    try {
      const { login_id } = await startZaloQrLogin(consentConfirmed);
      loginIdRef.current = login_id;
    } catch (e) {
      const detail = e instanceof ApiError ? (e.body as { detail?: unknown })?.detail : null;
      if (detail && typeof detail === 'object' && (detail as { code?: string }).code === 'consent_required') {
        setNeedConsent(true);
        return;
      }
      setStartError(typeof detail === 'string' ? detail : t('zaloqr.startError'));
    }
  }

  // Mở dialog → mở phiên login + poll trạng thái tới khi success/error
  useEffect(() => {
    if (!open) return;
    stoppedRef.current = false;
    setHandshake(null);
    setHandshakeError(false);
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
          // Không đóng ngay — chuyển sang bước handshake định danh acc chính.
          try {
            setHandshake(await mintLinkToken('zalo'));
          } catch {
            setHandshakeError(true);
          }
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
          {handshake || handshakeError ? (
            <div className="flex w-full flex-col gap-3">
              <p className="text-sm font-medium">{t('zaloqr.handshakeTitle')}</p>
              {handshakeError ? (
                <p className="text-sm text-destructive">{t('zaloqr.handshakeError')}</p>
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">
                    {t('zaloqr.handshakeDesc', { bot: handshake!.bot_name })}
                  </p>
                  <div className="flex items-center gap-2 rounded-lg border bg-muted/40 p-2">
                    <code className="flex-1 truncate font-mono text-sm">
                      /start {handshake!.token}
                    </code>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        navigator.clipboard?.writeText(`/start ${handshake!.token}`);
                        toast.success(t('zaloqr.handshakeCopied'));
                      }}
                    >
                      {t('zaloqr.handshakeCmd')}
                    </Button>
                  </div>
                </>
              )}
              <Button className="self-end" size="sm" onClick={onClose}>
                {t('zaloqr.handshakeDone')}
              </Button>
            </div>
          ) : needConsent ? (
            <div className="flex w-full flex-col gap-3">
              <p className="text-sm">{t('zaloqr.consentText')}</p>
              <label className="flex items-start gap-2 text-sm">
                <Checkbox
                  checked={consentChecked}
                  onCheckedChange={(v) => setConsentChecked(v === true)}
                  className="mt-0.5"
                />
                <span>
                  {t('zaloqr.consentCheckbox')}{' '}
                  <a href="/app/legal/terms" target="_blank" rel="noreferrer" className="underline underline-offset-4">
                    {t('legal.terms')}
                  </a>
                </span>
              </label>
              <Button className="self-end" size="sm" disabled={!consentChecked} onClick={() => begin(true)}>
                {t('zaloqr.consentContinue')}
              </Button>
            </div>
          ) : startError ? (
            <>
              <p className="text-sm text-destructive text-center">{startError}</p>
              <Button size="sm" variant="outline" onClick={() => begin()}>
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
              <Button size="sm" variant="outline" onClick={() => begin()}>
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
