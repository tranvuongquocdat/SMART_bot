import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { SendHorizontal } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { PageWrap, PageHeader } from '@/components/page-shell';
import {
  chatMessagesQuery,
  sendChatMessage,
  CHAT_STREAM_URL,
  type ChatMessage,
  type ChatStreamEvent,
} from './api';

type Bubble = {
  key: string;
  fromBot: boolean;
  senderName: string | null;
  text: string;
  ts: string;
};

function toBubble(m: ChatMessage): Bubble {
  return {
    key: `r-${m.kind}-${m.id}`,
    fromBot: m.kind === 'out',
    senderName: m.sender_name,
    text: m.text,
    ts: m.ts,
  };
}

function MessageBubble({ b }: { b: Bubble }) {
  const time = new Date(b.ts).toLocaleTimeString('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
  });
  return (
    <div className={`flex ${b.fromBot ? 'justify-start' : 'justify-end'}`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap break-words ${
          b.fromBot
            ? 'bg-card border text-foreground rounded-bl-sm'
            : 'bg-primary text-primary-foreground rounded-br-sm'
        }`}
      >
        <p>{b.text}</p>
        <p
          className={`mt-1 text-[10px] ${
            b.fromBot ? 'text-muted-foreground' : 'text-primary-foreground/70'
          }`}
        >
          {time}
        </p>
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { data: history } = useQuery(chatMessagesQuery());
  const [live, setLive] = useState<Bubble[]>([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const seenIds = useRef(new Set<string>());
  const bottomRef = useRef<HTMLDivElement>(null);

  // SSE: bot reply + echo tin nhắn của chính mình đều về qua stream
  useEffect(() => {
    const es = new EventSource(CHAT_STREAM_URL);
    es.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data) as ChatStreamEvent;
        if (ev.kind !== 'message' || seenIds.current.has(ev.msg_id)) return;
        seenIds.current.add(ev.msg_id);
        setLive((prev) => [
          ...prev,
          {
            key: `s-${ev.msg_id}`,
            fromBot: ev.sender_kind === 'bot',
            senderName: ev.sender_name,
            text: ev.text,
            ts: ev.ts,
          },
        ]);
      } catch {
        // bỏ qua heartbeat / event không parse được
      }
    };
    return () => es.close();
  }, []);

  const bubbles = [...(history ?? []).map(toBubble), ...live];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [bubbles.length]);

  async function handleSend() {
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      await sendChatMessage(text);
      setDraft('');
    } catch {
      toast.error('Không gửi được tin nhắn. Thử lại sau.');
    } finally {
      setSending(false);
    }
  }

  return (
    <PageWrap>
      <PageHeader
        title="Trợ lý"
        subtitle="Chat trực tiếp với thư ký ảo của bạn — giao việc, hỏi note, đặt lịch nhắc."
      />
      <div className="flex flex-col rounded-xl border bg-background/50 h-[calc(100vh-220px)] min-h-[420px]">
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {bubbles.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center mt-10">
              Chưa có tin nhắn. Hãy bắt đầu trò chuyện với trợ lý của bạn.
            </p>
          ) : (
            bubbles.map((b) => <MessageBubble key={b.key} b={b} />)
          )}
          <div ref={bottomRef} />
        </div>
        <div className="border-t p-3 flex gap-2">
          <textarea
            className="flex-1 resize-none rounded-lg border bg-card px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            rows={1}
            placeholder="Nhắn cho trợ lý…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          <Button size="icon" disabled={!draft.trim() || sending} onClick={handleSend}>
            <SendHorizontal className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </PageWrap>
  );
}
