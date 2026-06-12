import { useSuspenseQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Blocks, Plug2, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import {
  integrationsQuery, addMcpServer, toggleMcpServer, deleteMcpServer, togglePlugin,
} from './api';

function Switch({ on, onClick, disabled }: { on: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors disabled:opacity-50 ${
        on ? 'bg-primary' : 'bg-input'
      }`}
      role="switch"
      aria-checked={on}
    >
      <span
        className={`pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg transition-transform ${
          on ? 'translate-x-4' : 'translate-x-0'
        }`}
      />
    </button>
  );
}

export default function IntegrationsPage() {
  const t = useT();
  const { data } = useSuspenseQuery(integrationsQuery());
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ['admin', 'integrations'] });
  const errDetail = (e: unknown): string =>
    e instanceof ApiError && typeof (e.body as { detail?: string })?.detail === 'string'
      ? (e.body as { detail: string }).detail
      : t('common.actionFailed');

  const addMut = useMutation({
    mutationFn: addMcpServer,
    onSuccess: () => { invalidate(); toast.success(t('intg.addedToast')); },
    onError: (e) => toast.error(errDetail(e)),
  });
  const toggleMut = useMutation({
    mutationFn: toggleMcpServer,
    onSuccess: (d) => { invalidate(); toast.success(d.enabled ? t('common.on') : t('common.off')); },
    onError: (e) => toast.error(errDetail(e)),
  });
  const delMut = useMutation({
    mutationFn: deleteMcpServer,
    onSuccess: () => { invalidate(); toast.success(t('intg.removedToast')); },
    onError: (e) => toast.error(errDetail(e)),
  });
  const plugMut = useMutation({
    mutationFn: togglePlugin,
    onSuccess: (d) => { invalidate(); toast.success(d.enabled ? t('intg.pluginOn') : t('intg.pluginOff')); },
    onError: (e) => toast.error(errDetail(e)),
  });

  const addedCatalogIds = new Set(data.servers.map((s) => s.catalog_id));
  const available = data.catalog.filter((c) => !addedCatalogIds.has(c.id));

  return (
    <PageWrap className="max-w-[860px]">
      <PageHeader
        title={t('intg.title')}
        subtitle={
          data.mcp_slots === null
            ? t('intg.subtitle.unlimited')
            : t('intg.subtitle.capped', { used: data.mcp_used, total: data.mcp_slots })
        }
      />

      {/* Đã thêm */}
      <PageSection>
        <h2 className="text-sm font-semibold mb-3 text-muted-foreground">{t('intg.added')}</h2>
        {data.servers.length === 0 ? (
          <div className="rounded-xl border p-8 text-center text-sm text-muted-foreground">
            <Plug2 className="h-6 w-6 mx-auto mb-2 opacity-50" />
            {t('intg.addedEmpty')}
          </div>
        ) : (
          <div className="divide-y rounded-xl border">
            {data.servers.map((s) => (
              <div key={s.id} className="flex items-center gap-3 px-4 py-3">
                <Plug2 className="h-4 w-4 text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{s.name}</p>
                  <p className="text-xs text-muted-foreground truncate">{s.url}</p>
                </div>
                <Switch
                  on={s.enabled}
                  disabled={toggleMut.isPending}
                  onClick={() => toggleMut.mutate(s.id)}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                  onClick={() => delMut.mutate(s.id)}
                  aria-label={t('common.delete')}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </PageSection>

      {/* Danh mục */}
      <PageSection>
        <h2 className="text-sm font-semibold mb-3 text-muted-foreground">{t('intg.catalog')}</h2>
        {available.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {data.catalog.length === 0
              ? t('intg.catalogPreparing')
              : t('intg.catalogAllAdded')}
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {available.map((c) => (
              <div key={c.id} className="rounded-xl border p-4 flex flex-col gap-2">
                <p className="font-medium text-sm">{c.name}</p>
                <p className="text-xs text-muted-foreground flex-1">
                  {c.description || '—'}
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  className="self-start"
                  disabled={addMut.isPending}
                  onClick={() => addMut.mutate(c.id)}
                >
                  {t('common.add')}
                </Button>
              </div>
            ))}
          </div>
        )}
      </PageSection>

      {/* Plugins nội bộ */}
      <PageSection>
        <h2 className="text-sm font-semibold mb-3 text-muted-foreground">{t('intg.plugins')}</h2>
        {data.plugins.length === 0 ? (
          <div className="rounded-xl border p-8 text-center text-sm text-muted-foreground">
            <Blocks className="h-6 w-6 mx-auto mb-2 opacity-50" />
            {t('intg.pluginsEmpty')}
          </div>
        ) : (
          <div className="divide-y rounded-xl border">
            {data.plugins.map((p) => (
              <div key={p.plugin_id} className="flex items-center gap-3 px-4 py-3">
                <Blocks className="h-4 w-4 text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{p.name}</p>
                  {p.description && (
                    <p className="text-xs text-muted-foreground truncate">{p.description}</p>
                  )}
                </div>
                <Switch
                  on={p.enabled}
                  disabled={plugMut.isPending}
                  onClick={() => plugMut.mutate(p.plugin_id)}
                />
              </div>
            ))}
          </div>
        )}
      </PageSection>
    </PageWrap>
  );
}
