import { PageWrap, PageHeader } from '@/components/page-shell';
import { ChatPanel } from './chat-panel';

export default function ChatPage() {
  return (
    <PageWrap>
      <PageHeader
        title="Trợ lý"
        subtitle="Chat trực tiếp với thư ký ảo của bạn — giao việc, hỏi note, đặt lịch nhắc."
      />
      <ChatPanel className="h-[calc(100vh-220px)] min-h-[420px]" />
    </PageWrap>
  );
}
