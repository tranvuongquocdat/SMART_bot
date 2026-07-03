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
  const [uiLanguage, setUiLanguage] = useState<Lang>(lang);
  const [botLanguage, setBotLanguage] = useState('vi'); // vi | en | auto
  // Cửa sổ hội thoại: '' = theo mặc định hệ thống (null)
  const [histDm, setHistDm] = useState('');
  const [histGroup, setHistGroup] = useState('');

  useEffect(() => {
    if (data) {
      setName(data.name ?? '');
      setTz(data.tz ?? 'Asia/Ho_Chi_Minh');
      if (data.ui_language === 'vi' || data.ui_language === 'en') setUiLanguage(data.ui_language);
      setBotLanguage(data.language ?? 'vi');
      setHistDm(data.history_window_dm == null ? '' : String(data.history_window_dm));
      setHistGroup(data.history_window_group == null ? '' : String(data.history_window_group));
    }
  }, [data]);

  const mut = useMutation({
    mutationFn: () =>
      patchGeneral({
        name: name || undefined,
        tz: tz || undefined,
        language: botLanguage || undefined,
        ui_language: uiLanguage || undefined,
        history_window_dm: histDm === '' ? null : Number(histDm),
        history_window_group: histGroup === '' ? null : Number(histGroup),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: generalQuery.queryKey });
      toast.success(t('settings.general.saved'));
    },
    onError: () => toast.error(t('common.saveError')),
  });

  // Đổi ngôn ngữ giao diện → flip ngay (không cần bấm Lưu); Lưu để ghi vào tài khoản.
  const onUiLanguageChange = (v: string) => {
    const next = v as Lang;
    setUiLanguage(next);
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
        <Label htmlFor="gen-ui-lang">{t('settings.general.uiLanguage')}</Label>
        <Select value={uiLanguage} onValueChange={onUiLanguageChange}>
          <SelectTrigger id="gen-ui-lang">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="vi">{t('lang.vi')}</SelectItem>
            <SelectItem value="en">{t('lang.en')}</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">{t('settings.general.uiLanguageHint')}</p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="gen-bot-lang">{t('settings.general.botLanguage')}</Label>
        <Select value={botLanguage} onValueChange={setBotLanguage}>
          <SelectTrigger id="gen-bot-lang">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">{t('lang.auto')}</SelectItem>
            <SelectItem value="vi">{t('lang.vi')}</SelectItem>
            <SelectItem value="en">{t('lang.en')}</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">{t('settings.general.botLanguageHint')}</p>
      </div>

      <div className="space-y-2">
        <Label>{t('settings.general.historyWindow')}</Label>
        <div className="flex gap-3">
          <div className="flex-1 space-y-1">
            <p className="text-xs text-muted-foreground">{t('settings.general.historyDm')}</p>
            <Input
              type="number" min={0} max={50} value={histDm}
              onChange={(e) => setHistDm(e.target.value)}
              placeholder={t('settings.general.historyDefault', { n: data.history_window_dm_default ?? 12 })}
            />
          </div>
          <div className="flex-1 space-y-1">
            <p className="text-xs text-muted-foreground">{t('settings.general.historyGroup')}</p>
            <Input
              type="number" min={0} max={50} value={histGroup}
              onChange={(e) => setHistGroup(e.target.value)}
              placeholder={t('settings.general.historyDefault', { n: data.history_window_group_default ?? 12 })}
            />
          </div>
        </div>
        <p className="text-xs text-muted-foreground">{t('settings.general.historyHint')}</p>
      </div>

      <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
        {mut.isPending ? t('common.saving') : t('common.save')}
      </Button>
    </div>
  );
}
