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
import { startZaloQrLogin, zaloQrLoginStatus, type ZaloQrStatus } from './api';

const POLL_MS = 1500;

export function ZaloQrDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [state, setState] = useState<ZaloQrStatus | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const loginIdRef = useRef<string | null>(null);
  const stoppedRef = useRef(false);

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
          : 'Không mở được phiên đăng nhập. Thử lại sau.';
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
        if (s.status === 'success') {
          stoppedRef.current = true;
          toast.success(
            `Đã kết nối Zalo${s.display_name ? ` — ${s.display_name}` : ''}.`
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
          error: 'Phiên đăng nhập đã hết hạn.',
          bot_account_id: null,
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
          <DialogTitle>Kết nối Zalo</DialogTitle>
          <DialogDescription>
            Dùng tài khoản Zalo <strong>phụ</strong> (acc nghe ngóng của bạn) để quét — không
            dùng acc Zalo chính. Mở Zalo trên điện thoại → Cài đặt → Quét mã QR.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col items-center gap-3 py-2 min-h-[280px] justify-center">
          {startError ? (
            <>
              <p className="text-sm text-destructive text-center">{startError}</p>
              <Button size="sm" variant="outline" onClick={begin}>
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                Thử lại
              </Button>
            </>
          ) : status === 'qr' && state?.qr_image_b64 ? (
            <>
              <img
                src={`data:image/png;base64,${state.qr_image_b64}`}
                alt="QR đăng nhập Zalo"
                className="h-56 w-56 rounded-lg border bg-white p-2"
              />
              <p className="text-xs text-muted-foreground">Mã tự làm mới khi hết hạn.</p>
            </>
          ) : status === 'scanned' ? (
            <>
              <Smartphone className="h-10 w-10 text-primary" />
              <p className="text-sm text-center">
                Đã quét{state?.display_name ? ` bởi ${state.display_name}` : ''} — xác nhận
                đăng nhập trên điện thoại.
              </p>
            </>
          ) : status === 'error' ? (
            <>
              <p className="text-sm text-destructive text-center">
                {state?.error ?? 'Đăng nhập thất bại.'}
              </p>
              <Button size="sm" variant="outline" onClick={begin}>
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                Thử lại
              </Button>
            </>
          ) : (
            <>
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              <p className="text-sm text-muted-foreground">Đang tạo mã QR…</p>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
