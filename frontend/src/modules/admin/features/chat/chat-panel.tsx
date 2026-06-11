import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Paperclip, SendHorizontal, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  chatMessagesQuery,
  sendChatMessage,
  uploadChatFile,
  chatStreamUrl,
  type Attachment,
  type ChatMessage,
  type ChatStreamEvent,
} from './api';

const REPLY_TIMEOUT_MS = 90_000;

type Bubble = {
  key: string;
  fromBot: boolean;
  text: string;
  mediaKind: string | null;
  mediaUrl: string | null;
  ts: string;
  isError?: boolean;
};

function toBubble(m: ChatMessage): Bubble {
  return {
    key: `r-${m.kind}-${m.id}`,
    fromBot: m.kind === 'out',
    text: m.text ?? '',
    mediaKind: m.media_kind,
    mediaUrl: m.media_url,
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
          b.isError
            ? 'bg-destructive/10 border border-destructive/30 text-destructive rounded-bl-sm'
            : b.fromBot
              ? 'bg-card border text-foreground rounded-bl-sm'
              : 'bg-primary text-primary-foreground rounded-br-sm'
        }`}
      >
        {b.mediaUrl && b.mediaKind === 'image' && (
          <img
            src={b.mediaUrl}
            alt="đính kèm"
            className="rounded-lg mb-2 max-h-56 object-contain"
          />
        )}
        {b.mediaUrl && b.mediaKind !== 'image' && (
          <a
            href={b.mediaUrl}
            target="_blank"
            rel="noreferrer"
            className={`inline-flex items-center gap-1.5 mb-1.5 text-xs underline ${
              b.fromBot ? 'text-primary' : 'text-primary-foreground'
            }`}
          >
            <Paperclip className="h-3 w-3" />
            Tệp đính kèm
          </a>
        )}
        {b.text && <p>{b.text}</p>}
        <p
          className={`mt-1 text-[10px] ${
            b.isError
              ? 'text-destructive/70'
              : b.fromBot
                ? 'text-muted-foreground'
                : 'text-primary-foreground/70'
          }`}
        >
          {time}
        </p>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-card border rounded-2xl rounded-bl-sm px-4 py-3 inline-flex items-center gap-1.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-muted-foreground/60 animate-bounce"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  );
}

export function ChatPanel({
  conversationId,
  className = '',
}: {
  conversationId: string | null;
  className?: string;
}) {
  const { data: history } = useQuery(chatMessagesQuery(conversationId));
  const [live, setLive] = useState<Bubble[]>([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [awaitingReply, setAwaitingReply] = useState(false);
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const [uploading, setUploading] = useState(false);
  const seenIds = useRef(new Set<string>());
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Đổi hội thoại → reset state cục bộ
  useEffect(() => {
    setLive([]);
    seenIds.current.clear();
    setAwaitingReply(false);
    setAttachment(null);
  }, [conversationId]);

  useEffect(() => {
    const es = new EventSource(chatStreamUrl(conversationId));
    es.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data) as ChatStreamEvent;
        if (ev.kind !== 'message' || seenIds.current.has(ev.msg_id)) return;
        seenIds.current.add(ev.msg_id);
        if (ev.sender_kind === 'bot') {
          setAwaitingReply(false);
          if (timeoutRef.current) clearTimeout(timeoutRef.current);
        }
        setLive((prev) => [
          ...prev,
          {
            key: `s-${ev.msg_id}`,
            fromBot: ev.sender_kind === 'bot',
            text: ev.text,
            mediaKind: null,
            mediaUrl: null,
            ts: ev.ts,
          },
        ]);
      } catch {
        // heartbeat
      }
    };
    return () => es.close();
  }, [conversationId]);

  const bubbles = [...(history ?? []).map(toBubble), ...live];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [bubbles.length, awaitingReply]);

  async function handlePickFile(f: File) {
    setUploading(true);
    try {
      setAttachment(await uploadChatFile(f));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Tải tệp thất bại');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function handleSend() {
    const text = draft.trim();
    if ((!text && !attachment) || sending) return;
    setSending(true);
    try {
      await sendChatMessage({
        text,
        conversation_id: conversationId,
        attachment,
      });
      setDraft('');
      setAttachment(null);
      setAwaitingReply(true);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => {
        setAwaitingReply(false);
        setLive((prev) => [
          ...prev,
          {
            key: `err-${Date.now()}`,
            fromBot: true,
            isError: true,
            text: 'Trợ lý không phản hồi (quá 90 giây). Kiểm tra cấu hình model/API key trong Cài đặt > AI, hoặc thử lại.',
            mediaKind: null,
            mediaUrl: null,
            ts: new Date().toISOString(),
          },
        ]);
      }, REPLY_TIMEOUT_MS);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không gửi được tin nhắn');
    } finally {
      setSending(false);
    }
  }

  return (
    <div className={`flex flex-col rounded-xl border bg-background/50 ${className}`}>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {bubbles.length === 0 && !awaitingReply ? (
          <p className="text-sm text-muted-foreground text-center mt-10">
            Chưa có tin nhắn. Hãy bắt đầu trò chuyện với trợ lý của bạn.
          </p>
        ) : (
          bubbles.map((b) => <MessageBubble key={b.key} b={b} />)
        )}
        {awaitingReply && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {attachment && (
        <div className="px-3 pt-2 flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs bg-muted rounded-full px-3 py-1.5 max-w-[260px]">
            <Paperclip className="h-3 w-3 shrink-0" />
            <span className="truncate">{attachment.name}</span>
            <button onClick={() => setAttachment(null)} aria-label="Bỏ đính kèm">
              <X className="h-3 w-3" />
            </button>
          </span>
        </div>
      )}

      <div className="border-t p-3 flex gap-2 items-end">
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          accept=".jpg,.jpeg,.png,.gif,.webp,.pdf,.docx,.xlsx,.csv,.txt,.md"
          onChange={(e) => e.target.files?.[0] && handlePickFile(e.target.files[0])}
        />
        <Button
          size="icon"
          variant="ghost"
          disabled={uploading}
          onClick={() => fileRef.current?.click()}
          aria-label="Đính kèm tệp"
        >
          <Paperclip className={`h-4 w-4 ${uploading ? 'animate-pulse' : ''}`} />
        </Button>
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
        <Button
          size="icon"
          disabled={(!draft.trim() && !attachment) || sending}
          onClick={handleSend}
        >
          <SendHorizontal className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
