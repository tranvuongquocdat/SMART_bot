import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Maximize2, Minimize2, QrCode, RefreshCw, Smartphone, X } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusDot } from '@/components/status-dot';
import { formatNumber } from '@/lib/format';
import {
  accountQrLoginStatus,
  botAccountDailyStatsQuery,
  botAccountDetailQuery,
  botAccountMessagesQuery,
  startAccountQrLogin,
  type BotAccountDetail,
  type QrLoginStatus,
} from './api';

const MIN_W = 480;
const DEFAULT_W = 640;
const POLL_MS = 1500;

const TABS = [
  { key: 'overview', label: 'Tổng quan' },
  { key: 'connect', label: 'Kết nối' },
  { key: 'messages', label: 'Tin nhắn' },
] as const;
export type AccountTabKey = (typeof TABS)[number]['key'];

const ACCOUNT_STATUS_DOT: Record<string, 'ok' | 'warn' | 'err' | 'idle'> = {
  active: 'ok',
  rate_limited: 'warn',
  paused: 'warn',
  logged_out: 'err',
  banned: 'err',
};

const fmtCountdown = (s: number) =>
  `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

// ------------------------------------------------------------- Tổng quan

function OverviewTab({ d }: { d: BotAccountDetail }) {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-lg border bg-card px-3 py-2.5">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Tổng tin đã nhận
          </p>
          <p className="text-lg font-semibold tabular-nums">
            {formatNumber(d.msgs_received_total)}
          </p>
        </div>
        <div className="rounded-lg border bg-card px-3 py-2.5">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Tổng tin đã gửi
          </p>
          <p className="text-lg font-semibold tabular-nums">
            {formatNumber(d.msgs_sent_total)}
          </p>
        </div>
      </div>

      <div className="text-sm space-y-1.5">
        <p>
          <span className="text-muted-foreground">Trạng thái:</span>{' '}
          <StatusDot status={ACCOUNT_STATUS_DOT[d.status] ?? 'idle'} label={d.status} />
          {d.status_reason && (
            <span className="text-xs text-muted-foreground ml-2">({d.status_reason})</span>
          )}
        </p>
        <p>
          <span className="text-muted-foreground">UID:</span>{' '}
          <span className="font-mono text-xs">{d.provider_user_id}</span>
        </p>
        <p>
          <span className="text-muted-foreground">Phân bổ:</span>{' '}
          {d.ownership === 'boss_owned' ? `Riêng của boss #${d.owner_boss_id}` : 'Pool nền tảng'}
          {' · '}tối đa {d.max_assigned_bosses} boss
        </p>
        <p>
          <span className="text-muted-foreground">Hoạt động cuối:</span>{' '}
          {d.last_seen_at ? new Date(d.last_seen_at).toLocaleString('vi-VN') : 'Chưa có'}
        </p>
        <p>
          <span className="text-muted-foreground">Đăng nhập:</span>{' '}
          {d.has_credentials ? (
            <Badge variant="secondary" className="text-[10px]">Đã có session</Badge>
          ) : (
            <Badge variant="outline" className="text-[10px] text-destructive border-destructive/40">
              Chưa đăng nhập
            </Badge>
          )}
        </p>
      </div>

      <div>
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
          Boss đang dùng account này
        </p>
        {d.assignments.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa gán cho boss nào.</p>
        ) : (
          <ul className="space-y-1.5">
            {d.assignments.map((a) => (
              <li
                key={a.boss_id}
                className="flex items-center justify-between rounded-md border bg-card px-3 py-2 text-sm"
              >
                <span>
                  {a.boss_name ?? a.boss_email}
                  <span className="text-xs text-muted-foreground ml-2">{a.boss_email}</span>
                </span>
                <Badge
                  variant={a.status === 'active' ? 'default' : 'secondary'}
                  className="text-[10px]"
                >
                  {a.status}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------- Kết nối

function ConnectTab({ d, onLoggedIn }: { d: BotAccountDetail; onLoggedIn: () => void }) {
  const [state, setState] = useState<QrLoginStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const loginIdRef = useRef<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    loginIdRef.current = null;
    setRunning(false);
    setCountdown(null);
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  // Đếm ngược mượt 1s giữa các lần poll (poll đồng bộ lại giá trị từ server)
  useEffect(() => {
    if (countdown == null || countdown <= 0) return;
    const t = setTimeout(() => setCountdown((c) => (c == null ? null : c - 1)), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  async function begin() {
    setState(null);
    setRunning(true);
    try {
      const { login_id } = await startAccountQrLogin(d.id);
      loginIdRef.current = login_id;
    } catch {
      toast.error('Không mở được phiên đăng nhập.');
      setRunning(false);
      return;
    }
    timerRef.current = setInterval(async () => {
      const id = loginIdRef.current;
      if (!id) return;
      try {
        const s = await accountQrLoginStatus(id);
        setState(s);
        setCountdown(s.status === 'qr' || s.status === 'scanned' ? s.expires_in_s : null);
        if (s.status === 'success') {
          stopPolling();
          toast.success('Đã đăng nhập — listener đã khởi động lại.');
          onLoggedIn();
        } else if (s.status === 'error') {
          stopPolling();
        }
      } catch {
        stopPolling();
        setState({
          status: 'error',
          qr_image_b64: null,
          display_name: null,
          error: 'Phiên đăng nhập đã hết hạn.',
          bot_account_id: null,
          expires_in_s: 0,
        });
      }
    }, POLL_MS);
  }

  if (d.provider !== 'zalo') {
    return (
      <div className="text-sm text-muted-foreground space-y-2">
        <p>
          Kênh <span className="capitalize font-medium text-foreground">{d.provider}</span> không
          dùng đăng nhập QR.
        </p>
        {d.provider === 'telegram' && (
          <p>Telegram bot kết nối bằng token (cấu hình khi tạo bot với @BotFather).</p>
        )}
      </div>
    );
  }

  const status = state?.status;

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Quét QR bằng app Zalo của tài khoản <strong>{d.display_name ?? d.provider_user_id}</strong>{' '}
        (Cài đặt → Quét mã QR). Dùng cho đăng nhập lần đầu hoặc đăng nhập lại khi session hết hạn.
      </p>

      <div className="rounded-lg border bg-card min-h-[280px] flex flex-col items-center justify-center gap-3 p-4">
        {!running && !state && (
          <Button onClick={begin}>
            <QrCode className="h-4 w-4 mr-1.5" />
            {d.has_credentials ? 'Đăng nhập lại (QR)' : 'Đăng nhập QR'}
          </Button>
        )}
        {running && (!status || status === 'starting') && (
          <>
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Đang tạo mã QR…</p>
          </>
        )}
        {status === 'qr' && state?.qr_image_b64 && (
          <>
            <img
              src={`data:image/png;base64,${state.qr_image_b64}`}
              alt="QR đăng nhập Zalo"
              className="h-56 w-56 rounded-lg border bg-white p-2"
            />
            <p className="text-xs text-muted-foreground">
              Mã tự làm mới khi hết hạn
              {countdown != null && (
                <>
                  {' '}— phiên còn{' '}
                  <span className="font-mono font-medium text-foreground tabular-nums">
                    {fmtCountdown(countdown)}
                  </span>
                </>
              )}
            </p>
          </>
        )}
        {status === 'scanned' && (
          <>
            <Smartphone className="h-10 w-10 text-primary" />
            <p className="text-sm text-center">
              Đã quét{state?.display_name ? ` bởi ${state.display_name}` : ''} — xác nhận trên
              điện thoại.
            </p>
          </>
        )}
        {status === 'error' && (
          <>
            <p className="text-sm text-destructive text-center">
              {state?.error ?? 'Đăng nhập thất bại.'}
            </p>
            <Button size="sm" variant="outline" onClick={begin}>
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              Thử lại
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------- Tin nhắn

function MessagesTab({ accountId }: { accountId: number }) {
  const [days, setDays] = useState(30);
  const stats = useQuery(botAccountDailyStatsQuery(accountId, days));
  const recent = useQuery(botAccountMessagesQuery(accountId));

  const maxVal = Math.max(1, ...(stats.data ?? []).map((s) => s.received + s.sent));

  return (
    <div className="space-y-6">
      <section>
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Tin nhắn theo ngày
          </p>
          <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
            <SelectTrigger className="h-7 text-xs w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7 ngày</SelectItem>
              <SelectItem value="30">30 ngày</SelectItem>
              <SelectItem value="90">90 ngày</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {stats.isLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : (
          <div className="rounded-lg border overflow-hidden">
            <table className="w-full text-[13px]">
              <thead className="bg-[hsl(var(--bg-subtle))]">
                <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                  <th className="px-3 py-2 font-medium">Ngày</th>
                  <th className="px-3 py-2 font-medium text-right">Nhận</th>
                  <th className="px-3 py-2 font-medium text-right">Gửi</th>
                  <th className="px-3 py-2 font-medium w-[40%]"></th>
                </tr>
              </thead>
              <tbody>
                {(stats.data ?? []).map((s) => (
                  <tr key={s.date} className="border-t border-border">
                    <td className="px-3 py-1.5 text-muted-foreground whitespace-nowrap">
                      {new Date(s.date).toLocaleDateString('vi-VN', {
                        weekday: 'short',
                        day: '2-digit',
                        month: '2-digit',
                      })}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {s.received > 0 ? formatNumber(s.received) : '·'}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {s.sent > 0 ? formatNumber(s.sent) : '·'}
                    </td>
                    <td className="px-3 py-1.5">
                      <div className="flex h-2 rounded-full overflow-hidden bg-muted/40">
                        <div
                          className="bg-primary/70"
                          style={{ width: `${(s.received / maxVal) * 100}%` }}
                        />
                        <div
                          className="bg-primary/30"
                          style={{ width: `${(s.sent / maxVal) * 100}%` }}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="text-[11px] text-muted-foreground mt-1.5">
          <span className="inline-block h-2 w-3 rounded-sm bg-primary/70 mr-1 align-middle" />
          nhận
          <span className="inline-block h-2 w-3 rounded-sm bg-primary/30 ml-3 mr-1 align-middle" />
          gửi
        </p>
      </section>

      <section>
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
          Tin nhắn gần đây
        </p>
        {recent.isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : (recent.data ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có tin nhắn nào được ghi nhận.</p>
        ) : (
          <div className="rounded-lg border divide-y max-h-72 overflow-y-auto">
            {(recent.data ?? []).map((m, i) => (
              <div key={i} className="px-3 py-2 text-[13px]">
                <span className="text-muted-foreground mr-2">
                  {m.direction === 'in' ? '←' : '→'}
                </span>
                {m.text}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

// ----------------------------------------------------------------- Drawer

export function AccountDrawer({
  accountId,
  initialTab = 'overview',
  onClose,
}: {
  accountId: number;
  initialTab?: AccountTabKey;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const detail = useQuery(botAccountDetailQuery(accountId));
  const [tab, setTab] = useState<AccountTabKey>(initialTab);
  const [fullscreen, setFullscreen] = useState(false);
  const [width, setWidth] = useState(() => {
    const saved = localStorage.getItem('bot-account-drawer-w');
    return saved ? parseInt(saved, 10) : DEFAULT_W;
  });
  const dragging = useRef(false);

  const onDrag = useCallback((e: MouseEvent) => {
    if (!dragging.current) return;
    const w = Math.min(Math.max(window.innerWidth - e.clientX, MIN_W), window.innerWidth - 240);
    setWidth(w);
  }, []);

  useEffect(() => {
    const stop = () => {
      if (dragging.current) {
        dragging.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        setWidth((w) => {
          localStorage.setItem('bot-account-drawer-w', String(w));
          return w;
        });
      }
    };
    window.addEventListener('mousemove', onDrag);
    window.addEventListener('mouseup', stop);
    return () => {
      window.removeEventListener('mousemove', onDrag);
      window.removeEventListener('mouseup', stop);
    };
  }, [onDrag]);

  const refetchAll = () => {
    qc.invalidateQueries({ queryKey: ['superadmin', 'bot-accounts'] });
  };

  return (
    <>
      <div className="fixed inset-0 z-30 bg-black/10" onClick={onClose} />

      <aside
        className="fixed inset-y-0 right-0 z-40 bg-background border-l shadow-2xl flex flex-col"
        style={{ width: fullscreen ? '100vw' : width }}
      >
        {!fullscreen && (
          <div
            className="absolute inset-y-0 left-0 w-1.5 cursor-col-resize hover:bg-primary/30 transition-colors"
            onMouseDown={() => {
              dragging.current = true;
              document.body.style.cursor = 'col-resize';
              document.body.style.userSelect = 'none';
            }}
          />
        )}

        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b shrink-0">
          <div className="min-w-0">
            <p className="font-semibold truncate">
              {detail.data?.display_name ?? `Bot account #${accountId}`}
            </p>
            <p className="text-xs text-muted-foreground font-mono truncate">
              {detail.data?.provider} · {detail.data?.provider_user_id}
            </p>
          </div>
          {detail.data && (
            <Badge variant="secondary" className="text-[10px] capitalize">
              {detail.data.ownership ?? '—'}
            </Badge>
          )}
          <div className="ml-auto flex items-center gap-0.5">
            <button
              className="text-muted-foreground hover:text-foreground transition-colors p-1.5"
              onClick={() => setFullscreen((f) => !f)}
              aria-label={fullscreen ? 'Thu nhỏ' : 'Toàn màn hình'}
            >
              {fullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </button>
            <button
              className="text-muted-foreground hover:text-foreground transition-colors p-1.5"
              onClick={onClose}
              aria-label="Đóng"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-5 pt-3 border-b shrink-0">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-3 pb-2 text-sm transition-colors border-b-2 -mb-px ${
                tab === t.key
                  ? 'border-primary text-foreground font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          {detail.isLoading || !detail.data ? (
            <Skeleton className="h-60 w-full" />
          ) : tab === 'overview' ? (
            <OverviewTab d={detail.data} />
          ) : tab === 'connect' ? (
            <ConnectTab
              d={detail.data}
              onLoggedIn={() => {
                detail.refetch();
                refetchAll();
              }}
            />
          ) : (
            <MessagesTab accountId={accountId} />
          )}
        </div>
      </aside>
    </>
  );
}
