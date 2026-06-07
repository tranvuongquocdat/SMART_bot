import { Skeleton } from '@/components/ui/skeleton';

export function DashboardSkeleton() {
  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1140px] mx-auto space-y-5">
      <div className="space-y-2">
        <Skeleton className="h-7 w-72" />
        <Skeleton className="h-3.5 w-56" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-[78px] rounded-[12px]" />
        ))}
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <Skeleton className="h-[240px] rounded-[12px]" />
        <Skeleton className="h-[240px] rounded-[12px]" />
      </div>
      <Skeleton className="h-[200px] rounded-[12px]" />
    </div>
  );
}
