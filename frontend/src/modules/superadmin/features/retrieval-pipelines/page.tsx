import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MoreHorizontal, GitBranch } from 'lucide-react';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table';
import { EmptyState } from '@/components/empty-state';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { retrievalPipelinesQuery } from './api';
import type { RetrievalPipeline } from './api';
import { EditDialog } from './edit-dialog';
import { useI18n } from '@/lib/i18n';

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function RetrievalPipelinesPage() {
  const { t, lang } = useI18n();
  const locale = lang === 'en' ? 'en-US' : 'vi-VN';
  const pipelines = useQuery(retrievalPipelinesQuery);
  const [editTarget, setEditTarget] = useState<RetrievalPipeline | null>(null);

  const columns: ColumnDef<RetrievalPipeline>[] = [
    {
      header: 'Feature',
      accessorKey: 'feature',
      cell: ({ row }) => (
        <div className="font-medium font-mono text-sm">{row.original.feature}</div>
      ),
    },
    {
      header: 'Stages',
      accessorKey: 'stages_json',
      cell: ({ row }) => {
        const stages = row.original.stages_json;
        if (!stages || (stages as unknown[]).length === 0) {
          return <span className="text-muted-foreground text-sm">—</span>;
        }
        return (
          <pre className="text-xs text-muted-foreground whitespace-pre-wrap max-w-[280px]">
            {JSON.stringify(stages, null, 1)}
          </pre>
        );
      },
    },
    {
      header: t('sa.rp.colDesc'),
      accessorKey: 'description',
      cell: ({ row }) =>
        row.original.description ? (
          <span className="text-sm">{row.original.description}</span>
        ) : (
          <span className="text-muted-foreground text-sm">—</span>
        ),
    },
    {
      header: t('sa.rp.colUpdated'),
      accessorKey: 'updated_at',
      cell: ({ row }) => {
        const d = row.original.updated_at;
        if (!d) return <span className="text-muted-foreground">—</span>;
        return (
          <span className="text-sm text-muted-foreground">
            {new Date(d).toLocaleString(locale, {
              day: '2-digit',
              month: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        );
      },
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="text-right">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-[26px] w-[26px]">
                <MoreHorizontal className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setEditTarget(row.original)}>
                {t('sa.common.edit')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ),
    },
  ];

  return (
    <PageWrap>
      <PageHeader
        title={t('nav.sa.retrieval')}
        subtitle={t('sa.rp.subtitle')}
      />

      <PageSection>
        {pipelines.isLoading ? (
          <Skeleton className="h-[220px] rounded-[12px]" />
        ) : (
          <DataTable
            columns={columns}
            data={pipelines.data ?? []}
            mobileLabel={col => (typeof col.header === 'string' ? col.header : '')}
            empty={
              <EmptyState
                icon={GitBranch}
                title={t('sa.rp.empty')}
                description={t('sa.rp.emptyDesc')}
              />
            }
          />
        )}
      </PageSection>

      <EditDialog
        pipeline={editTarget}
        open={editTarget !== null}
        onOpenChange={v => !v && setEditTarget(null)}
      />
    </PageWrap>
  );
}
