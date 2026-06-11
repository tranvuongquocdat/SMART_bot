import { PageWrap, PageHeader } from '@/components/page-shell';
import AiTab from '../settings/ai-tab';

export default function AiModelsPage() {
  return (
    <PageWrap className="max-w-[860px]">
      <PageHeader
        title="Models AI"
        subtitle="Chọn model cho từng slot, đặt trần chi phí và quản lý API key riêng."
      />
      <AiTab />
    </PageWrap>
  );
}
