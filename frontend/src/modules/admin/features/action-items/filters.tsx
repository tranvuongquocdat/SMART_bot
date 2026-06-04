import { useSuspenseQuery } from '@tanstack/react-query';
import { groupsListQuery } from '../groups/api';
import { projectsQuery } from '../projects/api';
import type { ActionItemFilters } from './api';

const STATUS_OPTIONS = [
  { value: null, label: 'Tất cả' },
  { value: false, label: 'Đang làm' },
  { value: true, label: 'Đã xong' },
] as const;

type StatusOption = (typeof STATUS_OPTIONS)[number]['value'];

export function ActionItemFiltersBar({
  filters,
  onChange,
}: {
  filters: ActionItemFilters;
  onChange: (f: ActionItemFilters) => void;
}) {
  const { data: groups } = useSuspenseQuery(groupsListQuery());
  const { data: projects } = useSuspenseQuery(projectsQuery());

  return (
    <div className="flex flex-wrap gap-3 items-center">
      {/* Group filter */}
      <select
        value={filters.group_id ?? ''}
        onChange={e =>
          onChange({ ...filters, group_id: e.target.value ? Number(e.target.value) : null })
        }
        className="flex h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        <option value="">Tất cả nhóm</option>
        {groups.map(g => (
          <option key={g.id} value={g.id}>
            {g.name}
          </option>
        ))}
      </select>

      {/* Project filter */}
      <select
        value={filters.project_id ?? ''}
        onChange={e =>
          onChange({ ...filters, project_id: e.target.value ? Number(e.target.value) : null })
        }
        className="flex h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        <option value="">Tất cả dự án</option>
        {projects.map(p => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>

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
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
