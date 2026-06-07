import { useState, useRef } from 'react';
import { api } from '@/lib/api';

function readCsrfCookie(): string {
  const m = document.cookie.match(/(?:^|;\s*)smart_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      // Step 1: ensure CSRF cookie is set
      await api('/api/v1/auth/csrf', { method: 'GET' });

      const csrf = readCsrfCookie();
      const fd = new FormData(e.currentTarget);

      // Step 2: build a real form and submit it (full-page POST so the
      //         backend's 303 redirect to /app is followed naturally)
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/login';

      const fields: Record<string, string> = {
        email: fd.get('email') as string,
        password: fd.get('password') as string,
        next: '/app',
        _csrf: csrf,
      };

      for (const [name, value] of Object.entries(fields)) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = name;
        input.value = value;
        form.appendChild(input);
      }

      document.body.appendChild(form);
      form.submit();
      // browser navigates away — no cleanup needed
    } catch {
      setError('Lỗi kết nối, vui lòng thử lại.');
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="bg-card border border-border rounded-2xl shadow-lg p-8 w-full max-w-sm">
        {/* Brand */}
        <div className="flex flex-col items-center gap-2 mb-7">
          <div className="h-10 w-10 rounded-[11px] bg-gradient-to-br from-[hsl(168_72%_48%)] to-[hsl(190_75%_40%)] text-white font-bold text-base grid place-items-center shadow-[0_0_0_1px_hsl(168_50%_28%),inset_0_1px_0_hsl(168_80%_70%/0.3)]">
            S
          </div>
          <div className="text-center">
            <div className="text-lg font-semibold tracking-tight">SMART_bot</div>
            <div className="text-sm text-muted-foreground">Đăng nhập để tiếp tục</div>
          </div>
        </div>

        {/* Google OAuth */}
        <a
          href="/api/oauth/google/login"
          className="flex items-center justify-center gap-2 w-full border border-border rounded-lg py-2 px-4 text-sm font-medium hover:bg-accent transition-colors"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              fill="#4285F4"
            />
            <path
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              fill="#34A853"
            />
            <path
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
              fill="#FBBC05"
            />
            <path
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              fill="#EA4335"
            />
          </svg>
          Tiếp tục với Google
        </a>

        {/* Divider */}
        <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground">
          <span className="flex-1 border-t border-border" />
          <span>hoặc</span>
          <span className="flex-1 border-t border-border" />
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        {/* Email/password form */}
        <form ref={formRef} onSubmit={handleSubmit} className="space-y-3">
          <input
            name="email"
            type="email"
            required
            placeholder="Email"
            autoComplete="email"
            className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <input
            name="password"
            type="password"
            required
            placeholder="Mật khẩu"
            autoComplete="current-password"
            className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-foreground text-background rounded-lg py-2 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {loading ? 'Đang đăng nhập...' : 'Đăng nhập'}
          </button>
        </form>

        {/* Footer */}
        <p className="mt-5 text-center text-xs text-muted-foreground">
          Liên hệ admin nếu chưa có tài khoản
        </p>
      </div>
    </div>
  );
}
