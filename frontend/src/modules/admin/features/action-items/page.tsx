import { useState, Suspense } from 'react';
import { useSuspenseQuery } from '@tanstack/react-query';
import { ClipboardList } from 'lucide-react';
import { EmptyState } from '@/components/empty-state';
import { ActionItemFiltersBar } from './filters';
import { ItemRow } from './item-row';
import { actionItemsQuery, type ActionItemFilters } from './api';

function ItemsTable({ filters }: { filters: ActionItemFilters }) {
  const { data: items } = useSuspenseQuery(actionItemsQuery(filters));

  if (items.length === 0) {
    return (
      <EmptyState
        icon={ClipboardList}
        title="Không có việc nào"
        description="Không có việc cần làm khớp với bộ lọc này."
      />
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-muted-foreground border-b">
          <th className="p-3 w-10"></th>
          <th className="p-3">Nội dung</th>
          <th className="p-3">Nhóm</th>
          <th className="p-3">Giao cho</th>
          <th className="p-3 whitespace-nowrap">Hạn</th>
          <th className="p-3">Trạng thái</th>
        </tr>
      </thead>
      <tbody>
        {items.map(item => (
          <ItemRow key={item.id} item={item} filters={filters} />
        ))}
      </tbody>
    </table>
  );
}

export default function ActionItemsPage() {
  const [filters, setFilters] = useState<ActionItemFilters>({});

  return (
    <div className="flex flex-col gap-6 p-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Việc cần làm</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Tổng hợp việc cần làm từ tất cả các nhóm
        </p>
      </div>

      <Suspense fallback={<div className="h-9" />}>
        <ActionItemFiltersBar filters={filters} onChange={setFilters} />
      </Suspense>

      <div className="rounded-md border bg-card">
        <Suspense
          fallback={
            <div className="p-8 text-center text-muted-foreground text-sm">Đang tải...</div>
          }
        >
          <ItemsTable filters={filters} />
        </Suspense>
      </div>
    </div>
  );
}
