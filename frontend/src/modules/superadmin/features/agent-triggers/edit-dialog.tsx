import { useState, useEffect, type ChangeEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { createAgentTrigger, patchAgentTrigger } from './api';
import type { AgentTrigger } from './api';
import { useT } from '@/lib/i18n';

type Props = {
  trigger: AgentTrigger | null; // null = create mode
  open: boolean;
  onOpenChange: (v: boolean) => void;
};

function jsonStr(v: Record<string, unknown> | null | undefined): string {
  if (!v) return '';
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return '';
  }
}

function parseJson(s: string): Record<string, unknown> | null {
  const t = s.trim();
  if (!t) return null;
  try {
    return JSON.parse(t) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function EditDialog({ trigger, open, onOpenChange }: Props) {
  const t = useT();
  const qc = useQueryClient();
  const isEdit = trigger !== null;

  const [form, setForm] = useState({
    op_name: '',
    event_name: '',
    debounce: '',
    threshold: '',
    enabled: true,
  });
  const [jsonError, setJsonError] = useState('');

  useEffect(() => {
    if (trigger) {
      setForm({
        op_name: trigger.op_name,
        event_name: trigger.event_name,
        debounce: jsonStr(trigger.debounce_json),
        threshold: jsonStr(trigger.threshold_json),
        enabled: trigger.enabled,
      });
    } else {
      setForm({ op_name: '', event_name: '', debounce: '', threshold: '', enabled: true });
    }
    setJsonError('');
  }, [trigger, open]);

  const mutation = useMutation({
    mutationFn: () => {
      const debounce_json = parseJson(form.debounce);
      const threshold_json = parseJson(form.threshold);

      // Validate JSON inputs
      if (form.debounce.trim() && debounce_json === null) {
        throw new Error('debounce_json invalid JSON');
      }
      if (form.threshold.trim() && threshold_json === null) {
        throw new Error('threshold_json invalid JSON');
      }

      if (isEdit) {
        return patchAgentTrigger(trigger!.id, {
          enabled: form.enabled,
          debounce_json: debounce_json,
          threshold_json: threshold_json,
        });
      }
      return createAgentTrigger({
        op_name: form.op_name.trim(),
        event_name: form.event_name.trim(),
        debounce_json: debounce_json,
        threshold_json: threshold_json,
        enabled: form.enabled,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'agent-triggers'] });
      toast.success(isEdit ? t('sa.trig.updated') : t('sa.trig.created'));
      onOpenChange(false);
    },
    onError: (err: Error) => {
      if (err.message.includes('invalid JSON')) {
        setJsonError(err.message);
      } else {
        toast.error(isEdit ? t('sa.common.updateError') : t('sa.trig.createError'));
      }
    },
  });

  const set = (k: keyof typeof form, v: string | boolean) =>
    setForm(f => ({ ...f, [k]: v }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{isEdit ? t('sa.trig.editTitle') : t('sa.trig.addTitle')}</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          {!isEdit && (
            <>
              <div className="grid gap-1.5">
                <Label>Op name</Label>
                <Input
                  placeholder={t('sa.trig.opNamePlaceholder')}
                  value={form.op_name}
                  onChange={e => set('op_name', e.target.value)}
                />
              </div>
              <div className="grid gap-1.5">
                <Label>Event name</Label>
                <Input
                  placeholder={t('sa.trig.eventNamePlaceholder')}
                  value={form.event_name}
                  onChange={e => set('event_name', e.target.value)}
                />
              </div>
            </>
          )}

          <div className="grid gap-1.5">
            <Label>Debounce JSON</Label>
            <Textarea
              rows={3}
              className="font-mono text-xs"
              placeholder='{"window_s": 30}'
              value={form.debounce}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => {
                set('debounce', e.target.value);
                setJsonError('');
              }}
            />
          </div>

          <div className="grid gap-1.5">
            <Label>Threshold JSON</Label>
            <Textarea
              rows={3}
              className="font-mono text-xs"
              placeholder='{"min_count": 3}'
              value={form.threshold}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => {
                set('threshold', e.target.value);
                setJsonError('');
              }}
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="enabled"
              checked={form.enabled}
              onChange={e => set('enabled', e.target.checked)}
              className="h-4 w-4"
            />
            <Label htmlFor="enabled">Enabled</Label>
          </div>

          {jsonError && (
            <p className="text-xs text-destructive">{jsonError}</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('sa.common.cancel')}
          </Button>
          <Button
            disabled={
              mutation.isPending ||
              (!isEdit && (!form.op_name.trim() || !form.event_name.trim()))
            }
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? t('sa.common.saving') : t('sa.common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
