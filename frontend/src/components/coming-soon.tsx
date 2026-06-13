import { Construction } from 'lucide-react';
import { EmptyState } from './empty-state';
import { useT } from '@/lib/i18n';

export default function ComingSoon({ feature }: { feature: string }) {
  const t = useT();
  return (
    <EmptyState
      icon={Construction}
      title={t('comingSoon.title', { feature })}
      description={t('comingSoon.desc')}
    />
  );
}
