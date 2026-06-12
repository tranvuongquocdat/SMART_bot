import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useT, useI18n, type Lang } from '@/lib/i18n';
import { generalQuery, patchGeneral } from './api';

export default function GeneralTab() {
  const t = useT();
  const { lang, setLang } = useI18n();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery(generalQuery);

  const [name, setName] = useState('');
  const [tz, setTz] = useState('');
  const [language, setLanguage] = useState<Lang>(lang);

  useEffect(() => {
    if (data) {
      setName(data.name ?? '');
      setTz(data.tz ?? 'Asia/Ho_Chi_Minh');
      if (data.language === 'vi' || data.language === 'en') setLanguage(data.language);
    }
  }, [data]);

  const mut = useMutation({
    mutationFn: () =>
      patchGeneral({
        name: name || undefined,
        tz: tz || undefined,
        language: language || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: generalQuery.queryKey });
      toast.success(t('settings.general.saved'));
    },
    onError: () => toast.error(t('common.saveError')),
  });

  // Đổi ngôn ngữ → flip UI ngay (không cần bấm Lưu), Lưu để ghi vào tài khoản.
  const onLanguageChange = (v: string) => {
    const next = v as Lang;
    setLanguage(next);
    setLang(next);
  };

  if (isLoading) return <p className="text-sm text-muted-foreground">{t('common.loading')}</p>;
  if (!data) return null;

  return (
    <div className="space-y-4 max-w-md">
      <div className="space-y-2">
        <Label htmlFor="gen-name">{t('settings.general.displayName')}</Label>
        <Input
          id="gen-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('settings.general.displayNamePlaceholder')}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="gen-tz">{t('settings.general.tz')}</Label>
        <Input
          id="gen-tz"
          value={tz}
          onChange={(e) => setTz(e.target.value)}
          placeholder="Asia/Ho_Chi_Minh"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="gen-lang">{t('settings.general.language')}</Label>
        <Select value={language} onValueChange={onLanguageChange}>
          <SelectTrigger id="gen-lang">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="vi">{t('lang.vi')}</SelectItem>
            <SelectItem value="en">{t('lang.en')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
        {mut.isPending ? t('common.saving') : t('common.save')}
      </Button>
    </div>
  );
}
