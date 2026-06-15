import { useNavigate } from 'react-router-dom';
import { useTheme } from 'next-themes';
import { LogOut, SunMoon } from 'lucide-react';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command';
import type { NavSection } from '@/components/app-shell';
import { useT } from '@/lib/i18n';

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  nav: NavSection[];
};

export function CommandPalette({ open, onOpenChange, nav }: Props) {
  const navigate = useNavigate();
  const { theme, setTheme } = useTheme();
  const t = useT();

  const go = (href: string) => {
    onOpenChange(false);
    navigate(href);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder={t('cmd.placeholder')} />
      <CommandList>
        <CommandEmpty>{t('cmd.empty')}</CommandEmpty>
        {nav.map((section) => (
          <CommandGroup key={section.label} heading={t(section.label)}>
            {section.items.map((item) => (
              <CommandItem key={item.href} onSelect={() => go(item.href)}>
                <item.icon className="h-4 w-4" />
                <span>{t(item.label)}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
        <CommandSeparator />
        <CommandGroup heading={t('cmd.actions')}>
          <CommandItem
            onSelect={() => {
              setTheme(theme === 'light' ? 'dark' : 'light');
              onOpenChange(false);
            }}
          >
            <SunMoon className="h-4 w-4" />
            <span>{t('cmd.toggleTheme')}</span>
          </CommandItem>
          <CommandItem
            onSelect={() => {
              onOpenChange(false);
              window.location.href = '/logout';
            }}
          >
            <LogOut className="h-4 w-4" />
            <span>{t('cmd.logout')}</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
