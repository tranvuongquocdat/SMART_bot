import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Paperclip, SendHorizontal, Square, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  chatMessagesQuery,
  sendChatMessage,
  cancelChat,
  uploadChatFile,
  chatStreamUrl,
  type Attachment,
  type ChatMessage,
  type ChatStreamEvent,
} from './api';

const REPLY_TIMEOUT_MS = 90_000;

// Tin nhắn vừa gửi, hiển thị ngay trong lúc chờ server lưu xong (optimistic).
type PendingMessage = {
  key: string;
  text: string;
  attachmentName: string | null;
  ts: number;
};

function MessageBubble({ m }: { m: ChatMessage }) {
  const fromBot = m.kind === 'out';
  const time = new Date(m.ts).toLocaleTimeString('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
  });
  return (
    <div className={`flex ${fromBot ? 'justify-start' : 'justify-end'}`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap break-words ${
          fromBot
            ? 'bg-card border text-foreground rounded-bl-sm'
            : 'bg-primary text-primary-foreground rounded-br-sm'
        }`}
      >
        {m.media_url && m.media_kind === 'image' && (
          <img
            src={m.media_url}
            alt="đính kèm"
            className="rounded-lg mb-2 max-h-56 object-contain"
          />
        )}
        {m.media_url && m.media_kind !== 'image' && m.media_kind !== 'text' && (
          <a
            href={m.media_url}
            target="_blank"
            rel="noreferrer"
            className={`inline-flex items-center gap-1.5 mb-1.5 text-xs underline ${
              fromBot ? 'text-primary' : 'text-primary-foreground'
            }`}
          >
            <Paperclip className="h-3 w-3" />
            Tệp đính kèm
          </a>
        )}
        {m.text && <p>{m.text}</p>}
        <p
          className={`mt-1 text-[10px] ${
            fromBot ? 'text-muted-foreground' : 'text-primary-foreground/70'
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
  const qc = useQueryClient();
  const { data: messages = [] } = useQuery(chatMessagesQuery(conversationId));
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState<PendingMessage[]>([]);
  const [awaitingReply, setAwaitingReply] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const [uploading, setUploading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sentAtRef = useRef(0);

  const invalidateMessages = () =>
    qc.invalidateQueries({
      queryKey: ['admin', 'chat', 'messages', conversationId ?? 'default'],
    });

  // Đổi hội thoại → reset state cục bộ
  useEffect(() => {
    setAwaitingReply(false);
    setReplyError(null);
    setAttachment(null);
    setPending([]);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
  }, [conversationId]);

  // Tin optimistic đã xuất hiện trong lịch sử (server lưu xong) → gỡ bubble tạm.
  useEffect(() => {
    if (pending.length === 0) return;
    setPending((prev) =>
      prev.filter((p) => {
        const persisted = messages.some(
          (m) =>
            m.kind === 'in' &&
            Date.parse(m.ts) >= p.ts - 15_000 &&
            (m.text ?? '').startsWith(p.text)
        );
        const stale = Date.now() - p.ts > 60_000;
        return !persisted && !stale;
      })
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  // SSE chỉ là tín hiệu "có dữ liệu mới" — lịch sử DB là nguồn duy nhất,
  // tránh hiển thị đôi (echo + refetch cùng một tin).
  useEffect(() => {
    const es = new EventSource(chatStreamUrl(conversationId));
    es.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data) as ChatStreamEvent;
        if (ev.kind !== 'message') return;
        if (ev.sender_kind === 'bot') {
          setAwaitingReply(false);
          setReplyError(null);
          if (timeoutRef.current) clearTimeout(timeoutRef.current);
        }
        invalidateMessages();
      } catch {
        // heartbeat
      }
    };
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  // Bot có thể trả lời xong trước cả khi POST /send return (bus xử lý đồng
  // bộ) — nếu lịch sử đã có câu trả lời mới hơn thời điểm gửi thì tắt indicator.
  useEffect(() => {
    if (!awaitingReply) return;
    const replied = messages.some(
      (m) => m.kind === 'out' && Date.parse(m.ts) >= sentAtRef.current - 10_000
    );
    if (replied) {
      setAwaitingReply(false);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    }
  }, [messages, awaitingReply]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, pending.length, awaitingReply, replyError]);

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
    if (!text && !attachment) return;
    const sentAttachment = attachment;
    const key = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    // Tin rời input ngay — không khóa ô nhập, nhắn liên tục thoải mái,
    // server xếp hàng xử lý tuần tự.
    setDraft('');
    setAttachment(null);
    setPending((prev) => [
      ...prev,
      { key, text, attachmentName: sentAttachment?.name ?? null, ts: Date.now() },
    ]);
    setReplyError(null);
    setAwaitingReply(true);
    sentAtRef.current = Date.now();
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      setAwaitingReply(false);
      setReplyError(
        'Trợ lý không phản hồi (quá 90 giây). Kiểm tra cấu hình model/API key trong Cài đặt > AI, hoặc thử lại.'
      );
    }, REPLY_TIMEOUT_MS);
    try {
      await sendChatMessage({
        text,
        conversation_id: conversationId,
        attachment: sentAttachment,
      });
      invalidateMessages();
    } catch (e) {
      // Gửi hỏng → trả lại nội dung vào ô nhập để không mất tin
      setPending((prev) => prev.filter((p) => p.key !== key));
      setDraft((d) => d || text);
      if (sentAttachment) setAttachment((a) => a ?? sentAttachment);
      setAwaitingReply(false);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      toast.error(e instanceof Error ? e.message : 'Không gửi được tin nhắn');
    }
  }

  async function handleStop() {
    try {
      await cancelChat(conversationId);
    } catch {
      // server có thể đã xử lý xong — chỉ cần tắt indicator
    }
    setAwaitingReply(false);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
  }

  return (
    <div className={`flex flex-col rounded-xl border bg-background/50 ${className}`}>
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && pending.length === 0 && !awaitingReply ? (
          <p className="text-sm text-muted-foreground text-center mt-10">
            Chưa có tin nhắn. Hãy bắt đầu trò chuyện với trợ lý của bạn.
          </p>
        ) : (
          messages.map((m) => <MessageBubble key={`${m.kind}-${m.id}`} m={m} />)
        )}
        {pending.map((p) => (
          <div key={p.key} className="flex justify-end">
            <div className="max-w-[75%] rounded-2xl rounded-br-sm px-4 py-2.5 text-sm whitespace-pre-wrap break-words bg-primary/80 text-primary-foreground">
              {p.attachmentName && (
                <span className="inline-flex items-center gap-1.5 mb-1.5 text-xs underline text-primary-foreground">
                  <Paperclip className="h-3 w-3" />
                  {p.attachmentName}
                </span>
              )}
              {p.text && <p>{p.text}</p>}
              <p className="mt-1 text-[10px] text-primary-foreground/70">Đang gửi…</p>
            </div>
          </div>
        ))}
        {awaitingReply && <TypingIndicator />}
        {replyError && (
          <div className="flex justify-start">
            <div className="max-w-[75%] rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm bg-destructive/10 border border-destructive/30 text-destructive">
              {replyError}
            </div>
          </div>
        )}
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
        {awaitingReply && !draft.trim() && !attachment ? (
          <Button
            size="icon"
            variant="outline"
            onClick={handleStop}
            aria-label="Dừng trợ lý"
          >
            <Square className="h-3.5 w-3.5 fill-current" />
          </Button>
        ) : (
          <Button
            size="icon"
            disabled={!draft.trim() && !attachment}
            onClick={handleSend}
            aria-label="Gửi"
          >
            <SendHorizontal className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
}
