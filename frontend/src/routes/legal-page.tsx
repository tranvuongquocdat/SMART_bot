import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { marked } from 'marked';
import { api } from '@/lib/api';

const PROSE =
  'text-sm leading-[1.75] [&_h1]:text-xl [&_h1]:font-semibold [&_h1]:mb-3 ' +
  '[&_h2]:text-base [&_h2]:font-semibold [&_h2]:mt-6 [&_h2]:mb-2 ' +
  '[&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 ' +
  '[&_p]:my-2 [&_li]:my-1 [&_em]:text-muted-foreground ' +
  '[&_blockquote]:border-l-2 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground';

type LegalDoc = { kind: string; version: number; content_md: string; published_at: string };

/** Trang public /app/legal/terms | /app/legal/privacy — không cần đăng nhập. */
export default function LegalPage() {
  const { kind } = useParams();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['legal', kind],
    queryFn: () => api<LegalDoc>(`/api/v1/legal/${kind}`),
    enabled: kind === 'terms' || kind === 'privacy',
  });

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-2xl px-6 py-10">
        {isLoading && <p className="text-sm text-muted-foreground">…</p>}
        {isError && (
          <p className="text-sm text-muted-foreground">Tài liệu chưa được phát hành.</p>
        )}
        {data && (
          <>
            <div
              className={PROSE}
              dangerouslySetInnerHTML={{ __html: marked.parse(data.content_md) as string }}
            />
            <p className="mt-8 text-xs text-muted-foreground">
              Bản {data.version} — phát hành {new Date(data.published_at).toLocaleDateString('vi-VN')}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
