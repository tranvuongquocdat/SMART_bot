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
import { generalQuery, patchGeneral } from './api';

const LANGUAGE_OPTIONS = [
  { value: 'vi', label: 'Tiếng Việt' },
  { value: 'en', label: 'English' },
];

export default function GeneralTab() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery(generalQuery);

  const [name, setName] = useState('');
  const [tz, setTz] = useState('');
  const [language, setLanguage] = useState('vi');

  useEffect(() => {
    if (data) {
      setName(data.name ?? '');
      setTz(data.tz ?? 'Asia/Ho_Chi_Minh');
      setLanguage(data.language ?? 'vi');
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
      toast.success('Đã lưu cài đặt chung.');
    },
    onError: () => toast.error('Lưu thất bại.'),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Đang tải…</p>;
  if (!data) return null;

  return (
    <div className="space-y-4 max-w-md">
      <div className="space-y-2">
        <Label htmlFor="gen-name">Tên hiển thị</Label>
        <Input
          id="gen-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Tên hiển thị"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="gen-tz">Múi giờ</Label>
        <Input
          id="gen-tz"
          value={tz}
          onChange={(e) => setTz(e.target.value)}
          placeholder="Asia/Ho_Chi_Minh"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="gen-lang">Ngôn ngữ</Label>
        <Select value={language} onValueChange={setLanguage}>
          <SelectTrigger id="gen-lang">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LANGUAGE_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
        {mut.isPending ? 'Đang lưu…' : 'Lưu'}
      </Button>
    </div>
  );
}
