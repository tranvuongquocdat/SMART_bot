import { useState } from 'react';
import { Check, ChevronsUpDown } from 'lucide-react';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';

export type UserPickerOption = { id: string | number; label: string; sub?: string };

export function UserPicker({
  options,
  value,
  onChange,
  onSearchChange,
  placeholder,
}: {
  options: UserPickerOption[];
  value?: UserPickerOption['id'];
  onChange: (id: UserPickerOption['id']) => void;
  onSearchChange?: (q: string) => void;
  placeholder?: string;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const selected = options.find(o => o.id === value);
  const ph = placeholder ?? t('picker.choosePerson');

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" role="combobox" className="w-full justify-between font-normal">
          {selected ? selected.label : <span className="text-muted-foreground">{ph}</span>}
          <ChevronsUpDown className="ml-2 h-3.5 w-3.5 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command>
          <CommandInput placeholder={t('picker.searchByName')} onValueChange={onSearchChange} />
          <CommandList>
            <CommandEmpty>{t('picker.notFound')}</CommandEmpty>
            <CommandGroup>
              {options.map(o => (
                <CommandItem
                  key={o.id}
                  onSelect={() => { onChange(o.id); setOpen(false); }}
                  className="flex items-center justify-between"
                >
                  <div>
                    <div>{o.label}</div>
                    {o.sub && <div className="text-xs text-muted-foreground">{o.sub}</div>}
                  </div>
                  <Check className={cn('h-4 w-4', value === o.id ? 'opacity-100' : 'opacity-0')} />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
