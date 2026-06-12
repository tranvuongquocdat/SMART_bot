import { useSuspenseQuery } from '@tanstack/react-query';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useT } from '@/lib/i18n';
import { groupsListQuery } from '../groups/api';
import { projectsQuery } from '../projects/api';
import type { ActionItemFilters } from './api';

const STATUS_OPTIONS = [
  { value: null, key: 'ai.filter.allStatus' },
  { value: false, key: 'ai.status.doing' },
  { value: true, key: 'ai.status.done' },
] as const;

type StatusOption = (typeof STATUS_OPTIONS)[number]['value'];

export function ActionItemFiltersBar({
  filters,
  onChange,
}: {
  filters: ActionItemFilters;
  onChange: (f: ActionItemFilters) => void;
}) {
  const t = useT();
  const { data: groups } = useSuspenseQuery(groupsListQuery());
  const { data: projects } = useSuspenseQuery(projectsQuery());

  return (
    <div className="flex flex-wrap gap-3 items-center">
      {/* Group filter */}
      <Select
        value={filters.group_id != null ? String(filters.group_id) : 'all'}
        onValueChange={value =>
          onChange({ ...filters, group_id: value === 'all' ? null : Number(value) })
        }
      >
        <SelectTrigger className="w-auto min-w-[150px]">
          <SelectValue placeholder={t('ai.filter.allGroups')} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t('ai.filter.allGroups')}</SelectItem>
          {groups.map(g => (
            <SelectItem key={g.id} value={String(g.id)}>
              {g.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Project filter */}
      <Select
        value={filters.project_id != null ? String(filters.project_id) : 'all'}
        onValueChange={value =>
          onChange({ ...filters, project_id: value === 'all' ? null : Number(value) })
        }
      >
        <SelectTrigger className="w-auto min-w-[150px]">
          <SelectValue placeholder={t('ai.filter.allProjects')} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t('ai.filter.allProjects')}</SelectItem>
          {projects.map(p => (
            <SelectItem key={p.id} value={String(p.id)}>
              {p.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Status toggle */}
      <div className="flex rounded-md border overflow-hidden">
        {STATUS_OPTIONS.map(opt => (
          <button
            key={String(opt.value)}
            type="button"
            onClick={() => onChange({ ...filters, done: opt.value as StatusOption })}
            className={[
              'px-3 py-1.5 text-sm transition-colors',
              filters.done === opt.value
                ? 'bg-primary text-primary-foreground'
                : 'bg-transparent hover:bg-muted',
            ].join(' ')}
          >
            {t(opt.key)}
          </button>
        ))}
      </div>
    </div>
  );
}
