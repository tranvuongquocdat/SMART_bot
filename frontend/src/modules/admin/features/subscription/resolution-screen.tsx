import { Link } from 'react-router-dom';
import { AlertTriangle, ArrowRight, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { EffectiveLimits } from './api';

/**
 * Banner cảnh báo vượt limit — nằm inline trong nội dung trang (không phải
 * overlay full-screen), mỗi mục có link tới đúng trang để tắt bớt.
 */
export function ResolutionScreen({
  limits,
  onGoToUpgrade,
  onDismiss,
}: {
  limits: EffectiveLimits;
  onGoToUpgrade: () => void;
  onDismiss: () => void;
}) {
  const { over_limit } = limits;
  const items = [
    { label: 'Nhóm', count: over_limit.groups, href: '/app/admin/groups' },
    { label: 'Tools', count: over_limit.tools, href: '/app/admin/tools' },
    { label: 'Kênh', count: over_limit.channels, href: '/app/admin/channels' },
    { label: 'Integrations', count: over_limit.mcp, href: null },
  ].filter((i) => i.count > 0);

  return (
    <div className="rounded-xl border border-yellow-500/40 bg-yellow-500/5 p-5 space-y-4 mb-6">
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-yellow-500 shrink-0 mt-0.5" />
        <div className="flex-1">
          <h2 className="font-semibold">Vượt quá giới hạn gói</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Số tính năng đang bật vượt giới hạn gói hiện tại. Tắt bớt theo
            từng mục bên dưới, hoặc nâng cấp gói để tiếp tục.
          </p>
        </div>
        <button
          className="text-muted-foreground hover:text-foreground transition-colors"
          onClick={onDismiss}
          aria-label="Đóng cảnh báo"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <ul className="rounded-lg border border-border divide-y divide-border text-sm bg-card">
        {items.map((item) => (
          <li key={item.label} className="flex items-center px-4 py-2.5 gap-3">
            <span className="text-muted-foreground">{item.label}</span>
            <span className="text-destructive font-medium">vượt {item.count}</span>
            {item.href && (
              <Link
                to={item.href}
                className="ml-auto inline-flex items-center gap-1 text-primary hover:underline"
              >
                Tắt bớt <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            )}
          </li>
        ))}
      </ul>

      <Button size="sm" onClick={onGoToUpgrade}>
        Nâng cấp gói
      </Button>
    </div>
  );
}
