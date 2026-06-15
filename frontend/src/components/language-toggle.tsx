import { Languages } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useI18n, type Lang } from '@/lib/i18n';
import { patchGeneral } from '@/modules/admin/features/settings/api';

const LABELS: Record<Lang, string> = { vi: 'VI', en: 'EN' };

export function LanguageToggle() {
  const { lang, setLang, t } = useI18n();

  const pick = (l: Lang) => {
    setLang(l);
    // Ghi vào tài khoản để đồng bộ thiết bị khác (best-effort).
    patchGeneral({ ui_language: l }).catch(() => {});
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="h-[30px] px-2 rounded-[7px] grid place-items-center text-[hsl(var(--muted-foreground))] surface-section hover:bg-[hsl(var(--hover))] hover:text-foreground transition-colors inline-flex items-center gap-1 text-[11px] font-medium"
          aria-label="Ngôn ngữ / Language"
        >
          <Languages className="h-3.5 w-3.5" />
          {LABELS[lang]}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-36">
        <DropdownMenuItem onClick={() => pick('vi')} className={lang === 'vi' ? 'font-medium' : ''}>
          {t('lang.vi')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => pick('en')} className={lang === 'en' ? 'font-medium' : ''}>
          {t('lang.en')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
