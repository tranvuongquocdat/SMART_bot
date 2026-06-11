import { useState } from 'react';
import { useSuspenseQuery, useQueryClient } from '@tanstack/react-query';
import { Link2, MoreHorizontal, Plug, Unplug } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ApiError } from '@/lib/api';
import { StatusDot } from '@/components/status-dot';
import { EmptyState } from '@/components/empty-state';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { channelsQuery, connectChannel, disconnectChannel } from './api';
import type { Channel } from './api';

const PROVIDERS = ['zalo', 'telegram', 'lark'] as const;

function ChannelCard({ channel }: { channel: Channel }) {
  const qc = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleDisconnect() {
    setDeleting(true);
    try {
      await disconnectChannel(channel.provider);
      await qc.invalidateQueries({ queryKey: ['admin', 'channels'] });
      toast.success('Đã ngắt kết nối kênh.');
    } catch {
      toast.error('Không thể ngắt kết nối. Thử lại sau.');
    } finally {
      setDeleting(false);
      setConfirmOpen(false);
    }
  }

  const connectedAt = channel.connected_at
    ? new Date(channel.connected_at).toLocaleDateString('vi-VN')
    : null;

  return (
    <>
      <div className="flex items-center justify-between p-4 rounded-lg border bg-card">
        <div className="flex items-center gap-3">
          <Plug className="h-5 w-5 text-muted-foreground" />
          <div>
            <p className="font-medium capitalize">{channel.provider}</p>
            <p className="text-xs text-muted-foreground">
              {channel.display_name || '—'}
              {connectedAt && ` · ${connectedAt}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <StatusDot status={channel.status_dot} label={channel.status} />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                className="text-destructive"
                onClick={() => setConfirmOpen(true)}
              >
                <Unplug className="mr-2 h-4 w-4" />
                Ngắt kết nối
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ngắt kết nối kênh?</DialogTitle>
            <DialogDescription>
              Bot sẽ không còn hoạt động trên{' '}
              <span className="font-medium capitalize">{channel.provider}</span> nữa.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" disabled={deleting} onClick={() => setConfirmOpen(false)}>
              Hủy
            </Button>
            <Button variant="destructive" onClick={handleDisconnect} disabled={deleting}>
              Ngắt kết nối
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function ChannelsPage() {
  const { data: channels } = useSuspenseQuery(channelsQuery());
  const qc = useQueryClient();

  async function handleConnect(provider: string) {
    try {
      const result = await connectChannel(provider);
      await qc.invalidateQueries({ queryKey: ['admin', 'channels'] });
      toast.success(
        `Đã kết nối ${result.provider}${result.display_name ? ` — ${result.display_name}` : ''}.`
      );
    } catch (e) {
      const detail =
        e instanceof ApiError && typeof (e.body as { detail?: string })?.detail === 'string'
          ? (e.body as { detail: string }).detail
          : 'Không thể kết nối kênh. Thử lại sau.';
      toast.error(detail);
    }
  }

  return (
    <PageWrap>
      <PageHeader
        title="Kênh kết nối"
        subtitle="Quản lý kết nối với Zalo, Telegram, Lark và các nền tảng khác."
        actions={
          <div className="flex gap-2">
            {PROVIDERS.map(p => (
              <Button key={p} variant="outline" size="sm" onClick={() => handleConnect(p)}>
                <Plug className="mr-1.5 h-3.5 w-3.5" />
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </Button>
            ))}
          </div>
        }
      />

      <PageSection>
        {channels.length === 0 ? (
          <EmptyState
            icon={Link2}
            title="Chưa kết nối kênh nào"
            description="Nhấn nút bên trên để kết nối Zalo, Telegram hoặc Lark."
          />
        ) : (
          <div className="flex flex-col gap-3">
            {channels.map(ch => (
              <ChannelCard key={ch.provider} channel={ch} />
            ))}
          </div>
        )}
      </PageSection>
    </PageWrap>
  );
}
