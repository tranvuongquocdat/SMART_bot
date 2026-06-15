import { PageWrap, PageHeader } from '@/components/page-shell';
import { useT } from '@/lib/i18n';
import AiTab from '../settings/ai-tab';

export default function AiModelsPage() {
  const t = useT();
  return (
    <PageWrap className="max-w-[860px]">
      <PageHeader
        title={t('aitab.modelsTitle')}
        subtitle={t('aitab.modelsSubtitle')}
      />
      <AiTab />
    </PageWrap>
  );
}
