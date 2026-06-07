import { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { patchRetrievalPipeline } from './api';
import type { RetrievalPipeline } from './api';

type Props = {
  pipeline: RetrievalPipeline | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
};

export function EditDialog({ pipeline, open, onOpenChange }: Props) {
  const qc = useQueryClient();

  const [stagesRaw, setStagesRaw] = useState('');
  const [description, setDescription] = useState('');
  const [stagesError, setStagesError] = useState('');

  useEffect(() => {
    if (pipeline) {
      setStagesRaw(JSON.stringify(pipeline.stages_json, null, 2));
      setDescription(pipeline.description ?? '');
      setStagesError('');
    }
  }, [pipeline]);

  const mutation = useMutation({
    mutationFn: () => {
      let parsed: unknown[];
      try {
        parsed = JSON.parse(stagesRaw);
        if (!Array.isArray(parsed)) throw new Error('Must be array');
      } catch (e) {
        throw new Error('stages_json không hợp lệ: ' + (e as Error).message);
      }
      return patchRetrievalPipeline(pipeline!.feature, {
        stages_json: parsed,
        description: description || null,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'retrieval-pipelines'] });
      toast.success('Đã cập nhật pipeline');
      onOpenChange(false);
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Cập nhật thất bại');
    },
  });

  function handleSave() {
    setStagesError('');
    try {
      const parsed = JSON.parse(stagesRaw);
      if (!Array.isArray(parsed)) {
        setStagesError('Phải là JSON array');
        return;
      }
    } catch {
      setStagesError('JSON không hợp lệ');
      return;
    }
    mutation.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>Sửa pipeline: {pipeline?.feature}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="stages">Stages JSON</Label>
            <Textarea
              id="stages"
              rows={8}
              className="font-mono text-xs"
              value={stagesRaw}
              onChange={e => {
                setStagesRaw(e.target.value);
                setStagesError('');
              }}
              placeholder='[{"name":"bm25","k":50},{"name":"rrf"}]'
            />
            {stagesError && (
              <p className="text-xs text-destructive">{stagesError}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="description">Mô tả</Label>
            <Input
              id="description"
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Mô tả ngắn về pipeline"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Huỷ
          </Button>
          <Button onClick={handleSave} disabled={mutation.isPending}>
            {mutation.isPending ? 'Đang lưu...' : 'Lưu'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
