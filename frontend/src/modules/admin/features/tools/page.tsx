import { useSuspenseQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Wrench } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { toolsQuery, toggleTool, enableAllTools, disableAllTools } from './api';

export default function ToolsPage() {
  const { data: tools } = useSuspenseQuery(toolsQuery());
  const qc = useQueryClient();

  const mut = useMutation({
    mutationFn: (name: string) => toggleTool(name),
    onSuccess: (data) => {
      qc.setQueryData(['admin', 'tools'], (old: typeof tools) =>
        old?.map((t) => (t.name === data.name ? { ...t, active: data.active } : t)),
      );
      toast.success(data.active ? 'Đã bật tool' : 'Đã tắt tool');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const enableAllMut = useMutation({
    mutationFn: enableAllTools,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['admin', 'tools'] });
      if (data.limit !== null && data.active < data.total) {
        toast.info(
          `Đã bật ${data.active}/${data.total} tool — gói hiện tại giới hạn ${data.limit} tool.`
        );
      } else {
        toast.success(`Đã bật toàn bộ ${data.active} tool.`);
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const disableAllMut = useMutation({
    mutationFn: disableAllTools,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['admin', 'tools'] });
      toast.success(`Đã tắt ${data.disabled} tool.`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const active = tools.filter((t) => t.active);
  const inactive = tools.filter((t) => !t.active);

  return (
    <PageWrap className="max-w-[720px]">
      <PageHeader
        title="Tools"
        subtitle={`${active.length} / ${tools.length} tool đang bật.`}
        actions={
          <div className="flex gap-2">
            {active.length > 0 && (
              <Button
                size="sm"
                variant="outline"
                disabled={disableAllMut.isPending}
                onClick={() => disableAllMut.mutate()}
              >
                {disableAllMut.isPending ? 'Đang tắt…' : 'Tắt tất cả'}
              </Button>
            )}
            {inactive.length > 0 && (
              <Button
                size="sm"
                variant="outline"
                disabled={enableAllMut.isPending}
                onClick={() => enableAllMut.mutate()}
              >
                {enableAllMut.isPending ? 'Đang bật…' : 'Bật tất cả'}
              </Button>
            )}
          </div>
        }
      />

      {[
        { label: 'Đang bật', items: active },
        { label: 'Đã tắt', items: inactive },
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
