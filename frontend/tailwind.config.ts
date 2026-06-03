import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
        border: 'hsl(var(--border))',
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--foreground))' },
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
        destructive: { DEFAULT: 'hsl(var(--danger))', foreground: 'hsl(0 0% 100%)' },
        accent: { DEFAULT: 'hsl(var(--hover))', foreground: 'hsl(var(--foreground))' },
        ring: 'hsl(var(--primary))',
        ok: 'hsl(var(--ok))',
        warn: 'hsl(var(--warn))',
        info: 'hsl(var(--info))',
        dim: 'hsl(var(--dim))',
      },
      borderRadius: { lg: '10px', md: '8px', sm: '6px' },
      fontFamily: {
        sans: ['"Inter var"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
} satisfies Config;
