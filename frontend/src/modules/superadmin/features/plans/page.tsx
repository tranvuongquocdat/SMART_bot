import { useState } from 'react';
import { useSuspenseQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { plansAdminQuery, createPlan, updatePlan, type SAPlan, type PlanLimits } from './api';

function parseLimits(raw: string | PlanLimits): PlanLimits {
  if (typeof raw === 'string') {
    try { return JSON.parse(raw); } catch { return {}; }
  }
  return raw;
}

function LimitField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null | undefined;
  onChange: (v: number | null) => void;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Input
        type="number"
        placeholder="∞ (để trống)"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        className="h-8 text-sm"
      />
    </div>
  );
}

type FormState = {
  name: string;
  label: string;
  sort_order: string;
  limits: PlanLimits;
};

const emptyForm = (): FormState => ({
  name: '',
  label: '',
  sort_order: '',
  limits: {},
});

function fromPlan(plan: SAPlan): FormState {
  return {
    name: plan.name,
    label: plan.label,
    sort_order: String(plan.sort_order),
    limits: parseLimits(plan.limits_json),
  };
}

function PlanModal({
  plan,
  open,
  onClose,
}: {
  plan: SAPlan | null;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<FormState>(plan ? fromPlan(plan) : emptyForm());

  const isEdit = !!plan;

  const mut = useMutation({
    mutationFn: () => {
      const limits = form.limits;
      const sort_order = form.sort_order ? Number(form.sort_order) : undefined;
      if (isEdit) {
        return updatePlan(plan!.id, { label: form.label, limits_json: limits, sort_order });
      }
      return createPlan({ name: form.name, label: form.label, limits_json: limits, sort_order });
    },
    onSuccess: () => {
      toast.success(isEdit ? 'Đã cập nhật gói' : 'Đã tạo gói');
      qc.invalidateQueries({ queryKey: ['superadmin', 'plans'] });
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const setLimit = (key: keyof PlanLimits) => (v: number | null) =>
    setForm((f) => ({ ...f, limits: { ...f.limits, [key]: v } }));

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Sửa gói' : 'Tạo gói mới'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {!isEdit && (
            <div className="space-y-1.5">
              <Label>Tên (name)</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="starter"
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label>Nhãn (label)</Label>
            <Input
              value={form.label}
              onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
              placeholder="Starter"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Thứ tự</Label>
            <Input
              type="number"
              value={form.sort_order}
              onChange={(e) => setForm((f) => ({ ...f, sort_order: e.target.value }))}
              placeholder="1"
              className="h-8 w-24"
            />
          </div>
          <div className="space-y-2">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Giới hạn
            </p>
            <div className="grid grid-cols-2 gap-3">
              <LimitField label="Nhóm tối đa" value={form.limits.max_active_groups} onChange={setLimit('max_active_groups')} />
              <LimitField label="Tools tối đa" value={form.limits.max_active_tools} onChange={setLimit('max_active_tools')} />
              <LimitField label="Kênh tối đa" value={form.limits.max_active_channels} onChange={setLimit('max_active_channels')} />
              <LimitField label="MCP slots" value={form.limits.mcp_slots} onChange={setLimit('mcp_slots')} />
              <LimitField label="Số ngày" value={form.limits.duration_days} onChange={setLimit('duration_days')} />
              <LimitField label="Chi phí USD/ngày" value={form.limits.cost_cap_usd_daily} onChange={setLimit('cost_cap_usd_daily')} />
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={mut.isPending}>
            Huỷ
          </Button>
          <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
            {mut.isPending ? 'Đang lưu...' : isEdit ? 'Lưu' : 'Tạo'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function SAPlansPage() {
  const { data: plans } = useSuspenseQuery(plansAdminQuery());
  const qc = useQueryClient();
  const [editTarget, setEditTarget] = useState<SAPlan | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const toggleActive = useMutation({
    mutationFn: (plan: SAPlan) =>
      updatePlan(plan.id, { is_active: !plan.is_active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'plans'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <PageWrap className="max-w-[800px]">
      <PageHeader title="Gói dịch vụ" subtitle="Quản lý các gói cước và giới hạn." />

      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCreateOpen(true)} className="gap-1.5">
          <Plus className="h-4 w-4" />
          Tạo gói
        </Button>
      </div>

      <PageSection>
        <div className="divide-y divide-border rounded-xl border">
          {plans.map((plan) => {
            const limits = parseLimits(plan.limits_json);
            return (
              <div key={plan.id} className="flex items-center gap-3 px-4 py-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{plan.label}</span>
                    <span className="text-xs text-muted-foreground">({plan.name})</span>
                    {!plan.is_active && (
                      <Badge variant="outline" className="text-xs">Ẩn</Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {[
                      limits.max_active_groups != null ? `${limits.max_active_groups} nhóm` : '∞ nhóm',
                      limits.max_active_tools != null ? `${limits.max_active_tools} tools` : '∞ tools',
                      limits.max_active_channels != null ? `${limits.max_active_channels} kênh` : '∞ kênh',
                      limits.duration_days != null ? `${limits.duration_days}d` : null,
                    ].filter(Boolean).join(' · ')}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => toggleActive.mutate(plan)}
                    disabled={toggleActive.isPending}
                    className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors disabled:opacity-50 ${
                      plan.is_active ? 'bg-primary' : 'bg-input'
                    }`}
                    role="switch"
                    aria-checked={plan.is_active}
                  >
                    <span
                      className={`block h-4 w-4 rounded-full bg-background shadow-lg transition-transform ${
                        plan.is_active ? 'translate-x-4' : 'translate-x-0'
                      }`}
                    />
                  </button>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => setEditTarget(plan)}
                    className="h-7 w-7"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </PageSection>

      <PlanModal
        plan={editTarget}
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
      />
      <PlanModal
        plan={null}
        open={createOpen}
        onClose={() => setCreateOpen(false)}
      />
    </PageWrap>
  );
}
