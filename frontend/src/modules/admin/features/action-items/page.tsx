import { useState, Suspense } from 'react';
import { useSuspenseQuery } from '@tanstack/react-query';
import { ClipboardList } from 'lucide-react';
import { EmptyState } from '@/components/empty-state';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { useT } from '@/lib/i18n';
import { ActionItemFiltersBar } from './filters';
import { ItemRow } from './item-row';
import { actionItemsQuery, type ActionItemFilters } from './api';

function ItemsTable({ filters }: { filters: ActionItemFilters }) {
  const t = useT();
  const { data: items } = useSuspenseQuery(actionItemsQuery(filters));

  if (items.length === 0) {
    return (
      <EmptyState
        icon={ClipboardList}
        title={t('ai.empty.title')}
        description={t('ai.empty.desc')}
      />
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-muted-foreground border-b">
          <th className="p-3 w-10"></th>
          <th className="p-3">{t('ai.col.content')}</th>
          <th className="p-3">{t('ai.col.group')}</th>
          <th className="p-3">{t('ai.col.assignee')}</th>
          <th className="p-3 whitespace-nowrap">{t('ai.col.due')}</th>
          <th className="p-3">{t('ai.col.status')}</th>
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
  const t = useT();
  const [filters, setFilters] = useState<ActionItemFilters>({});

  return (
    <PageWrap>
      <PageHeader title={t('ai.title')} subtitle={t('ai.subtitle')} />

      <PageSection>
        <Suspense fallback={<div className="h-9" />}>
          <ActionItemFiltersBar filters={filters} onChange={setFilters} />
        </Suspense>
      </PageSection>

      <PageSection className="rounded-[12px] bg-card-grad surface-section overflow-hidden">
        <Suspense
          fallback={
            <div className="p-8 text-center text-muted-foreground text-sm">{t('common.loadingShort')}</div>
          }
        >
          <ItemsTable filters={filters} />
        </Suspense>
      </PageSection>
    </PageWrap>
  );
}
