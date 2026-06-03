import { Construction } from 'lucide-react';
import { EmptyState } from './empty-state';

export default function ComingSoon({ feature }: { feature: string }) {
  return (
    <EmptyState
      icon={Construction}
      title={`${feature} — đang phát triển`}
      description="Tính năng này thuộc Sub-Project 2; trang này là placeholder."
    />
  );
}
