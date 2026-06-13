import { Lightbulb, LightbulbOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toggleTheme } from '@/lib/theme';
import { useState } from 'react';
import { useT } from '@/lib/i18n';

export function ThemeToggle() {
  const t = useT();
  const [tick, setTick] = useState(0);
  const isLight = document.documentElement.classList.contains('light');
  return (
    <Button
      variant="outline"
      size="icon"
      aria-label={t('common.toggleTheme')}
      onClick={() => {
        toggleTheme();
        setTick(n => n + 1);
      }}
      className="h-[30px] w-[30px]"
    >
      {isLight ? (
        <Lightbulb className="h-4 w-4 text-amber-500" />
      ) : (
        <LightbulbOff className="h-4 w-4" />
      )}
      <span className="sr-only">{tick}</span>
    </Button>
  );
}
