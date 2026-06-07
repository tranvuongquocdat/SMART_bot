import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MoreHorizontal, GitBranch } from 'lucide-react';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table';
import { EmptyState } from '@/components/empty-state';
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

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function RetrievalPipelinesPage() {
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
      header: 'Mô tả',
      accessorKey: 'description',
      cell: ({ row }) =>
        row.original.description ? (
          <span className="text-sm">{row.original.description}</span>
        ) : (
          <span className="text-muted-foreground text-sm">—</span>
        ),
    },
    {
      header: 'Cập nhật',
      accessorKey: 'updated_at',
      cell: ({ row }) => {
        const d = row.original.updated_at;
        if (!d) return <span className="text-muted-foreground">—</span>;
        return (
          <span className="text-sm text-muted-foreground">
            {new Date(d).toLocaleString('vi-VN', {
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
                Sửa
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ),
    },
  ];

  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1140px]">
      <header className="mb-8">
        <h1 className="text-[24px] font-semibold tracking-tight">Retrieval pipelines</h1>
        <p className="text-muted-foreground mt-1.5">
          Cấu hình stages và mô tả cho từng pipeline retrieval.
        </p>
      </header>

      {pipelines.isLoading ? (
        <Skeleton className="h-[220px] rounded-[10px]" />
      ) : (
        <DataTable
          columns={columns}
          data={pipelines.data ?? []}
          mobileLabel={col => (typeof col.header === 'string' ? col.header : '')}
          empty={
            <EmptyState
              icon={GitBranch}
              title="Chưa có pipeline nào"
              description="Dữ liệu sẽ xuất hiện khi có pipeline được cấu hình."
            />
          }
        />
      )}

      <EditDialog
        pipeline={editTarget}
        open={editTarget !== null}
        onOpenChange={v => !v && setEditTarget(null)}
      />
    </div>
  );
}
