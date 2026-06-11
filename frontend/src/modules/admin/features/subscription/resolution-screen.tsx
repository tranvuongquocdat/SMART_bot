import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { EffectiveLimits } from './api';

export function ResolutionScreen({
  limits,
  onGoToUpgrade,
}: {
  limits: EffectiveLimits;
  onGoToUpgrade: () => void;
}) {
  const { over_limit } = limits;
  const items = [
    { label: 'Nhóm', count: over_limit.groups },
    { label: 'Tools', count: over_limit.tools },
    { label: 'Kênh', count: over_limit.channels },
    { label: 'Integrations', count: over_limit.mcp },
  ].filter((i) => i.count > 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/90 backdrop-blur">
      <div className="max-w-md w-full mx-4 rounded-2xl border border-border bg-card p-8 shadow-xl space-y-5">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-6 w-6 text-yellow-500 shrink-0 mt-0.5" />
          <div>
            <h2 className="font-semibold text-lg">Vượt quá giới hạn gói</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Số tính năng đang bật vượt giới hạn gói hiện tại. Vui lòng tắt
              bớt hoặc nâng cấp gói để tiếp tục sử dụng.
            </p>
          </div>
        </div>

        <ul className="rounded-lg border border-border divide-y text-sm">
          {items.map((item) => (
            <li
              key={item.label}
              className="flex justify-between px-4 py-2.5"
            >
              <span className="text-muted-foreground">{item.label}</span>
              <span className="text-destructive font-medium">
                vượt {item.count}
              </span>
            </li>
          ))}
        </ul>

        <p className="text-xs text-muted-foreground">
          Vào trang Nhóm / Tools / Kênh để tắt bớt, hoặc đăng ký gói cao hơn
          bên dưới.
        </p>

        <Button className="w-full" onClick={onGoToUpgrade}>
          Nâng cấp gói
        </Button>
      </div>
    </div>
  );
}
