import { useState } from 'react';
import {
  useSuspenseQuery, useMutation, useQueryClient, queryOptions,
} from '@tanstack/react-query';
import { Plug2, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';

type CatalogItem = {
  id: number;
  name: string;
  description: string | null;
  url: string;
  icon_url: string | null;
  is_active: boolean;
  created_at: string;
};

const catalogQuery = () =>
  queryOptions({
    queryKey: ['superadmin', 'mcp-catalog'],
    queryFn: () => api<CatalogItem[]>('/api/v1/superadmin/mcp-catalog'),
  });

function errDetail(e: unknown): string {
  return e instanceof ApiError && typeof (e.body as { detail?: string })?.detail === 'string'
    ? (e.body as { detail: string }).detail
    : 'Thao tác thất bại';
}

export default function McpCatalogPage() {
  const { data } = useSuspenseQuery(catalogQuery());
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [desc, setDesc] = useState('');

  const invalidate = () => qc.invalidateQueries({ queryKey: ['superadmin', 'mcp-catalog'] });

  const createMut = useMutation({
    mutationFn: () =>
      api('/api/v1/superadmin/mcp-catalog', {
        method: 'POST',
        body: JSON.stringify({ name, url, description: desc || null }),
      }),
    onSuccess: () => {
      invalidate();
      setOpen(false);
      setName(''); setUrl(''); setDesc('');
      toast.success('Đã thêm vào danh mục');
    },
    onError: (e) => toast.error(errDetail(e)),
  });

  const toggleMut = useMutation({
    mutationFn: (item: CatalogItem) =>
      api(`/api/v1/superadmin/mcp-catalog/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !item.is_active }),
      }),
    onSuccess: invalidate,
    onError: (e) => toast.error(errDetail(e)),
  });

  const delMut = useMutation({
    mutationFn: (id: number) =>
      api(`/api/v1/superadmin/mcp-catalog/${id}`, { method: 'DELETE' }),
    onSuccess: () => { invalidate(); toast.success('Đã xoá'); },
    onError: (e) => toast.error(errDetail(e)),
  });

  return (
    <PageWrap className="max-w-[860px]">
      <PageHeader
        title="MCP Catalog"
        subtitle="Danh mục integration đã kiểm duyệt — boss chọn từ đây theo slot của gói."
        actions={<Button size="sm" onClick={() => setOpen(true)}>+ Thêm MCP</Button>}
      />
      <PageSection>
        {data.length === 0 ? (
          <div className="rounded-xl border p-8 text-center text-sm text-muted-foreground">
            <Plug2 className="h-6 w-6 mx-auto mb-2 opacity-50" />
            Chưa có MCP nào trong danh mục.
          </div>
        ) : (
          <div className="divide-y rounded-xl border">
            {data.map((item) => (
              <div key={item.id} className="flex items-center gap-3 px-4 py-3">
                <Plug2 className="h-4 w-4 text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">
                    {item.name}
                    {!item.is_active && (
                      <span className="ml-2 text-xs text-muted-foreground">(ẩn)</span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {item.url}
                    {item.description && ` — ${item.description}`}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs"
                  onClick={() => toggleMut.mutate(item)}
                >
                  {item.is_active ? 'Ẩn' : 'Hiện'}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                  onClick={() => delMut.mutate(item.id)}
                  aria-label="Xoá"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </PageSection>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Thêm MCP vào danh mục</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Tên</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Google Calendar" />
            </div>
            <div className="space-y-1.5">
              <Label>URL MCP server</Label>
              <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
            </div>
            <div className="space-y-1.5">
              <Label>Mô tả <span className="text-muted-foreground text-xs">(tuỳ chọn)</span></Label>
              <Input value={desc} onChange={(e) => setDesc(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Huỷ</Button>
            <Button
              disabled={!name.trim() || !url.trim() || createMut.isPending}
              onClick={() => createMut.mutate()}
            >
              {createMut.isPending ? 'Đang thêm…' : 'Thêm'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageWrap>
  );
}
