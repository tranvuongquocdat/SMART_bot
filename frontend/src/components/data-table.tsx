import type { ReactNode } from 'react';
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { cn } from '@/lib/utils';

export type DataTableProps<T> = {
  columns: ColumnDef<T, any>[];
  data: T[];
  mobileLabel?: (col: ColumnDef<T, any>) => string;
  empty?: ReactNode;
};

export function DataTable<T>({ columns, data, mobileLabel, empty }: DataTableProps<T>) {
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });

  if (data.length === 0 && empty) return <>{empty}</>;

  return (
    <div className="rounded-[10px] bg-card shadow-[var(--shadow-card,0_0_0_1px_hsl(var(--border-strong)),0_1px_2px_rgba(0,0,0,.04))] overflow-hidden">
      <table className="w-full text-[13px]">
        <thead className="bg-[hsl(var(--bg-subtle))]">
          {table.getHeaderGroups().map(hg => (
            <tr key={hg.id}>
              {hg.headers.map(h => (
                <th
                  key={h.id}
                  className="text-left font-medium text-muted-foreground px-4 py-2.5 text-[11.5px] uppercase tracking-wide border-b border-border max-md:hidden"
                >
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map(row => (
            <tr
              key={row.id}
              className={cn(
                'transition-colors hover:bg-[hsl(var(--hover))]',
                'max-md:block max-md:p-3.5 max-md:border-b max-md:border-border'
              )}
            >
              {row.getVisibleCells().map(cell => (
                <td
                  key={cell.id}
                  data-label={mobileLabel ? mobileLabel(cell.column.columnDef) : ''}
                  className={cn(
                    'px-4 py-3 border-b border-border align-middle',
                    'max-md:block max-md:px-0 max-md:py-1 max-md:border-0',
                    'max-md:flex max-md:justify-between max-md:items-center max-md:gap-3',
                    'max-md:before:content-[attr(data-label)] max-md:before:text--[hsl(var(--dim))] max-md:before:text-[11px] max-md:before:uppercase max-md:before:tracking-wide'
                  )}
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
