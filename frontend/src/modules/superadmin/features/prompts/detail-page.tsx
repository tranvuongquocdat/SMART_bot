import { useState, useEffect, type ChangeEvent } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Save, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { promptDetailQuery, createPrompt, patchPrompt } from './api';

export default function PromptDetailPage() {
  const { id } = useParams<{ id: string }>();
  const promptId = Number(id);
  const qc = useQueryClient();

  const detail = useQuery(promptDetailQuery(promptId));

  const [body, setBody] = useState('');
  const [notes, setNotes] = useState('');
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (detail.data) {
      setBody(detail.data.body);
      setNotes(detail.data.notes ?? '');
      setDirty(false);
    }
  }, [detail.data]);

  // Create a new version (same key, auto-incremented version)
  const saveMut = useMutation({
    mutationFn: () =>
      createPrompt({
        key: detail.data!.key,
        body,
        notes: notes.trim() || null,
      }),
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'prompts'] });
      toast.success(`Đã lưu version mới (id=${data.id})`);
      setDirty(false);
    },
    onError: () => toast.error('Lưu thất bại'),
  });

  const activateMut = useMutation({
    mutationFn: () => patchPrompt(promptId, { is_active: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'prompts', promptId] });
      qc.invalidateQueries({ queryKey: ['superadmin', 'prompts'] });
      toast.success('Đã kích hoạt');
    },
    onError: () => toast.error('Kích hoạt thất bại'),
  });

  if (detail.isLoading) {
    return (
      <div className="px-10 py-8 max-w-[860px]">
        <Skeleton className="h-[400px] rounded-[10px]" />
      </div>
    );
  }

  if (!detail.data) {
    return (
      <div className="px-10 py-8">
        <p className="text-muted-foreground">Không tìm thấy prompt.</p>
      </div>
    );
  }

  const row = detail.data;

  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[860px]">
      <Link
        to="/app/superadmin/prompts"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Danh sách prompts
      </Link>

      <header className="mb-6">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-[22px] font-semibold tracking-tight">
            {row.key}
            <span className="text-base text-muted-foreground ml-2">v{row.version}</span>
          </h1>
          {row.is_active ? (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-50 text-green-700 border border-green-200">
              active
            </span>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              disabled={activateMut.isPending}
              onClick={() => activateMut.mutate()}
            >
              <Zap className="h-3 w-3 mr-1" />
              Kích hoạt
            </Button>
          )}
        </div>
        {row.notes && (
          <p className="text-sm text-muted-foreground mt-1">{row.notes}</p>
        )}
      </header>

      <div className="grid gap-5">
        <div className="grid gap-1.5">
          <Label>Body</Label>
          <Textarea
            rows={16}
            className="font-mono text-xs resize-y"
            value={body}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => {
              setBody(e.target.value);
              setDirty(true);
            }}
          />
        </div>

        <div className="grid gap-1.5">
          <Label>Ghi chú cho version mới</Label>
          <Input
            placeholder="vd: fix tone"
            value={notes}
            onChange={(e: ChangeEvent<HTMLInputElement>) => {
              setNotes(e.target.value);
              setDirty(true);
            }}
          />
        </div>

        <div className="flex justify-end">
          <Button
            disabled={saveMut.isPending || !dirty}
            onClick={() => saveMut.mutate()}
          >
            <Save className="h-3.5 w-3.5 mr-1.5" />
            {saveMut.isPending ? 'Đang lưu...' : 'Lưu phiên bản mới'}
          </Button>
        </div>
      </div>
    </div>
  );
}
