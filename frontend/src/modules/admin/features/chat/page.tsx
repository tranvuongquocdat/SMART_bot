import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { MessageCirclePlus, Pencil, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { PageWrap, PageHeader } from '@/components/page-shell';
import { useT } from '@/lib/i18n';
import { ChatPanel } from './chat-panel';
import {
  conversationsQuery,
  createConversation,
  renameConversation,
  deleteConversation,
} from './api';

export default function ChatPage() {
  const t = useT();
  const qc = useQueryClient();
  const { data: conversations = [] } = useQuery(conversationsQuery());
  const [selected, setSelected] = useState<string | null>(null);

  const activeId = selected ?? conversations[0]?.id ?? null;

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ['admin', 'chat', 'conversations'] });

  const createMut = useMutation({
    mutationFn: () => createConversation(),
    onSuccess: (c) => {
      invalidate();
      setSelected(c.id);
    },
    onError: () => toast.error(t('chat.createError')),
  });

  const renameMut = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      renameConversation(id, name),
    onSuccess: invalidate,
    onError: () => toast.error(t('chat.renameError')),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteConversation(id),
    onSuccess: (_d, id) => {
      invalidate();
      if (activeId === id) setSelected(null);
      toast.success(t('chat.deleted'));
    },
    onError: () => toast.error(t('common.deleteError')),
  });

  return (
    <PageWrap className="max-w-[1280px]">
      <PageHeader
        title={t('chat.title')}
        subtitle={t('chat.subtitle')}
        actions={
          <Button size="sm" onClick={() => createMut.mutate()} disabled={createMut.isPending}>
            <MessageCirclePlus className="h-4 w-4 mr-1.5" />
            {t('chat.newConversation')}
          </Button>
        }
      />
      <div className="grid grid-cols-[280px_1fr] gap-5 items-start max-md:grid-cols-1">
        {/* Sidebar hội thoại */}
        <div className="rounded-xl border divide-y overflow-hidden">
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`group px-3 py-2.5 cursor-pointer transition-colors ${
                c.id === activeId ? 'bg-primary/10' : 'hover:bg-muted/40'
              }`}
              onClick={() => setSelected(c.id)}
            >
              <div className="flex items-center gap-1.5">
                <p className="text-sm font-medium truncate flex-1">{c.name}</p>
                <button
                  className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-foreground transition-opacity"
                  onClick={(e) => {
                    e.stopPropagation();
                    const name = window.prompt(t('chat.renamePrompt'), c.name);
                    if (name?.trim()) renameMut.mutate({ id: c.id, name: name.trim() });
                  }}
                  aria-label={t('chat.rename')}
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                <button
                  className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-opacity"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (window.confirm(t('chat.deleteConfirm', { name: c.name })))
                      deleteMut.mutate(c.id);
                  }}
                  aria-label={t('common.delete')}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              {c.last_message && (
                <p className="text-xs text-muted-foreground truncate mt-0.5">
                  {c.last_message}
                </p>
              )}
            </div>
          ))}
          {conversations.length === 0 && (
            <p className="text-xs text-muted-foreground p-4 text-center">{t('common.loading')}</p>
          )}
        </div>

        <ChatPanel
          key={activeId ?? 'none'}
          conversationId={activeId}
          className="h-[calc(100vh-210px)] min-h-[480px]"
        />
      </div>
    </PageWrap>
  );
}
