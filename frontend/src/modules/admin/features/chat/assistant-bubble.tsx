import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { MessageCircle, X } from 'lucide-react';
import { ChatPanel } from './chat-panel';

/**
 * Bong bóng trợ lý nổi góc phải-dưới, hiện trên mọi trang admin.
 * Lịch sử chat nằm ở server — mỗi lần mở panel refetch + reconnect SSE,
 * nên đóng mở không mất tin nhắn.
 */
export function AssistantBubble() {
  const [open, setOpen] = useState(false);
  const location = useLocation();

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
            className="fixed bottom-24 right-6 z-50 w-[380px] max-w-[calc(100vw-3rem)]"
          >
            <div className="rounded-xl shadow-2xl bg-background border overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2.5 border-b bg-card">
                <p className="text-sm font-semibold">Trợ lý</p>
                <button
                  className="text-muted-foreground hover:text-foreground transition-colors"
                  onClick={() => setOpen(false)}
                  aria-label="Đóng trợ lý"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <ChatPanel className="h-[480px] max-h-[60vh] border-0 rounded-none" />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <button
        className="fixed bottom-6 right-6 z-50 h-12 w-12 rounded-full bg-primary text-primary-foreground shadow-lg hover:opacity-90 transition-opacity flex items-center justify-center"
        onClick={() => setOpen((v) => !v)}
        aria-label="Mở trợ lý"
      >
        {open ? <X className="h-5 w-5" /> : <MessageCircle className="h-5 w-5" />}
      </button>
    </>
  );
}
