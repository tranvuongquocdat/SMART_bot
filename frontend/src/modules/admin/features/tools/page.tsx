import { useSuspenseQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Wrench } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { useT } from '@/lib/i18n';
import { toolsQuery, toggleTool, enableAllTools, disableAllTools } from './api';

export default function ToolsPage() {
  const t = useT();
  const { data: tools } = useSuspenseQuery(toolsQuery());
  const qc = useQueryClient();

  const mut = useMutation({
    mutationFn: (name: string) => toggleTool(name),
    onSuccess: (data) => {
      qc.setQueryData(['admin', 'tools'], (old: typeof tools) =>
        old?.map((tl) => (tl.name === data.name ? { ...tl, active: data.active } : tl)),
      );
      toast.success(data.active ? t('tools.enabled') : t('tools.disabled'));
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const enableAllMut = useMutation({
    mutationFn: enableAllTools,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['admin', 'tools'] });
      if (data.limit !== null && data.active < data.total) {
        toast.info(
          t('tools.enabledCapped', { active: data.active, total: data.total, limit: data.limit })
        );
      } else {
        toast.success(t('tools.enabledAll', { active: data.active }));
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const disableAllMut = useMutation({
    mutationFn: disableAllTools,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['admin', 'tools'] });
      toast.success(t('tools.disabledN', { n: data.disabled }));
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const active = tools.filter((t) => t.active);
  const inactive = tools.filter((t) => !t.active);

  return (
    <PageWrap className="max-w-[720px]">
      <PageHeader
        title={t('tools.title')}
        subtitle={t('tools.subtitle', { active: active.length, total: tools.length })}
        actions={
          <div className="flex gap-2">
            {active.length > 0 && (
              <Button
                size="sm"
                variant="outline"
                disabled={disableAllMut.isPending}
                onClick={() => disableAllMut.mutate()}
              >
                {disableAllMut.isPending ? t('tools.disabling') : t('tools.disableAll')}
              </Button>
            )}
            {inactive.length > 0 && (
              <Button
                size="sm"
                variant="outline"
                disabled={enableAllMut.isPending}
                onClick={() => enableAllMut.mutate()}
              >
                {enableAllMut.isPending ? t('tools.enabling') : t('tools.enableAll')}
              </Button>
            )}
          </div>
        }
      />

      {[
        { label: t('tools.section.active'), items: active },
        { label: t('tools.section.inactive'), items: inactive },
      ].map(({ label, items }) =>
        items.length === 0 ? null : (
          <PageSection key={label}>
            <h2 className="text-sm font-semibold mb-3 text-muted-foreground">{label}</h2>
            <div className="divide-y divide-border rounded-xl border">
              {items.map((tool) => (
                <div
                  key={tool.name}
                  className="flex items-center gap-3 px-4 py-3"
                >
                  <Wrench className="h-4 w-4 text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">{tool.name}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {tool.description}
                    </p>
                  </div>
                  <button
                    onClick={() => mut.mutate(tool.name)}
                    disabled={mut.isPending && mut.variables === tool.name}
                    className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                      tool.active ? 'bg-primary' : 'bg-input'
                    }`}
                    role="switch"
                    aria-checked={tool.active}
                  >
                    <span
                      className={`pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg ring-0 transition-transform ${
                        tool.active ? 'translate-x-4' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              ))}
            </div>
          </PageSection>
        ),
      )}
    </PageWrap>
  );
}
