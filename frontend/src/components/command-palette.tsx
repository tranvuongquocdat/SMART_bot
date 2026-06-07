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

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  nav: NavSection[];
};

export function CommandPalette({ open, onOpenChange, nav }: Props) {
  const navigate = useNavigate();
  const { theme, setTheme } = useTheme();

  const go = (href: string) => {
    onOpenChange(false);
    navigate(href);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Tìm trang, hành động…" />
      <CommandList>
        <CommandEmpty>Không tìm thấy.</CommandEmpty>
        {nav.map((section) => (
          <CommandGroup key={section.label} heading={section.label}>
            {section.items.map((item) => (
              <CommandItem key={item.href} onSelect={() => go(item.href)}>
                <item.icon className="h-4 w-4" />
                <span>{item.label}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
        <CommandSeparator />
        <CommandGroup heading="Hành động">
          <CommandItem
            onSelect={() => {
              setTheme(theme === 'light' ? 'dark' : 'light');
              onOpenChange(false);
            }}
          >
            <SunMoon className="h-4 w-4" />
            <span>Đổi chế độ sáng/tối</span>
          </CommandItem>
          <CommandItem
            onSelect={() => {
              onOpenChange(false);
              window.location.href = '/logout';
            }}
          >
            <LogOut className="h-4 w-4" />
            <span>Đăng xuất</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
