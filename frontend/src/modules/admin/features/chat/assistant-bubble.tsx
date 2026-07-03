import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { MessageCircle, MessageCirclePlus, X } from 'lucide-react';
import { toast } from 'sonner';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useT } from '@/lib/i18n';
import { ChatPanel } from './chat-panel';
import { conversationsQuery, createConversation } from './api';

/**
 * Bong bóng trợ lý nổi góc phải-dưới, hiện trên mọi trang admin.
 * Có chọn hội thoại + tạo hội thoại mới ngay trong header panel.
 */
export function AssistantBubble() {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const location = useLocation();
  const qc = useQueryClient();
  const { data: conversations = [] } = useQuery({
    ...conversationsQuery(),
    enabled: open,
  });

  const activeId = selected ?? conversations[0]?.id ?? null;

  const createMut = useMutation({
    mutationFn: () => createConversation(),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['admin', 'chat', 'conversations'] });
      setSelected(c.id);
    },
    onError: () => toast.error(t('chat.createError')),
  });

  // Trang Trợ lý full-screen đã có chat — ẩn bong bóng để khỏi trùng
  if (location.pathname.endsWith('/admin/chat')) return null;

  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.div
            key="assistant-panel"
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="fixed bottom-24 right-6 z-50 w-[560px] max-w-[calc(100vw-3rem)]"
          >
            <div className="rounded-xl shadow-2xl bg-background border overflow-hidden">
              <div className="flex items-center gap-2 px-3 py-2 border-b bg-card">
                <div className="flex-1 min-w-0">
                  <Select
                    value={activeId ?? undefined}
                    onValueChange={(v) => setSelected(v)}
                  >
                    <SelectTrigger className="h-8 text-sm border-0 shadow-none bg-transparent px-2">
                      <SelectValue placeholder={t('chat.assistant')} />
                    </SelectTrigger>
                    <SelectContent>
                      {conversations.map((c) => (
                        <SelectItem key={c.id} value={c.id}>
                          {c.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <button
                  className="text-muted-foreground hover:text-foreground transition-colors p-1"
                  onClick={() => createMut.mutate()}
                  aria-label={t('chat.newConversation')}
                  title={t('chat.newConversation')}
                >
                  <MessageCirclePlus className="h-4 w-4" />
                </button>
                <button
                  className="text-muted-foreground hover:text-foreground transition-colors p-1"
                  onClick={() => setOpen(false)}
                  aria-label={t('chat.closeAssistant')}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <ChatPanel
                key={activeId ?? 'none'}
                conversationId={activeId}
                className="h-[640px] max-h-[78vh] border-0 rounded-none"
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <button
        className="fixed bottom-6 right-6 z-50 h-12 w-12 rounded-full bg-primary text-primary-foreground shadow-lg hover:opacity-90 transition-opacity flex items-center justify-center"
        onClick={() => setOpen((v) => !v)}
        aria-label={t('chat.openAssistant')}
      >
        {open ? <X className="h-5 w-5" /> : <MessageCircle className="h-5 w-5" />}
      </button>
    </>
  );
}
