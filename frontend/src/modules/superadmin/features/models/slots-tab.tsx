import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { RefreshCw, Zap, Eye } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { SlotCard } from './slot-card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { slotsQuery, modelsQuery, patchModelSlot } from './api';
import type { Slot, Model } from './api';

const SLOT_ICONS = { smart: RefreshCw, fast: Zap, vision: Eye } as const;

function AssignSlotDialog({
  slot,
  models,
  open,
  onOpenChange,
}: {
  slot: Slot;
  models: Model[];
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const eligibleModels = models.filter(
    m => m.tier === slot.slot && m.is_active,
  );
  const [selectedId, setSelectedId] = useState<number | null>(slot.model_id);

  const mutation = useMutation({
    mutationFn: () => patchModelSlot(slot.slot, selectedId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'model-slots'] });
      qc.invalidateQueries({ queryKey: ['superadmin', 'models'] });
      toast.success(`Đã cập nhật slot ${slot.slot}`);
      onOpenChange(false);
    },
    onError: () => toast.error('Cập nhật slot thất bại'),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Gán model cho slot <span className="capitalize">{slot.slot}</span></DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3 mt-2">
          <div className="flex flex-col gap-1.5">
            <Label>Model</Label>
            {eligibleModels.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Chưa có model nào với tier <strong>{slot.slot}</strong>. Hãy thêm model ở tab Models trước.
              </p>
            ) : (
              <select
                value={selectedId ?? ''}
                onChange={e => setSelectedId(Number(e.target.value))}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {eligibleModels.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.provider})
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
        <DialogFooter className="mt-4">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Huỷ</Button>
          <Button
            disabled={!selectedId || eligibleModels.length === 0 || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            Lưu
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function SlotsTab() {
  const slots = useQuery(slotsQuery);
  const models = useQuery(modelsQuery);
  const [editSlot, setEditSlot] = useState<Slot | null>(null);

  return (
    <section>
      <div className="flex items-end justify-between mb-3.5 gap-3 flex-wrap">
        <div>
          <h2 className="text-[14.5px] font-semibold tracking-tight">Model slots</h2>
          <p className="text-[12.5px] text-muted-foreground mt-0.5">
            Boss có thể override; đây là giá trị mặc định nền tảng.
          </p>
        </div>
      </div>
      {slots.isLoading ? (
        <div className="grid grid-cols-3 gap-3 max-md:grid-cols-1">
          {[0, 1, 2].map(i => <Skeleton key={i} className="h-[180px] rounded-[10px]" />)}
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-3 max-md:grid-cols-1">
          {slots.data?.map(s => (
            <div key={s.slot} onClick={() => setEditSlot(s)} className="cursor-pointer">
              <SlotCard slot={s} icon={SLOT_ICONS[s.slot]} />
            </div>
          ))}
        </div>
      )}
      {editSlot && models.data && (
        <AssignSlotDialog
          slot={editSlot}
          models={models.data}
          open={!!editSlot}
          onOpenChange={open => { if (!open) setEditSlot(null); }}
        />
      )}
    </section>
  );
}
