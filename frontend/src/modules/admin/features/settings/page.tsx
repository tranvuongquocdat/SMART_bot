import { useSearchParams } from 'react-router-dom';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import AccountTab from './account-tab';
import GeneralTab from './general-tab';

const VALID_TABS = ['account', 'ai', 'general'] as const;

export default function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get('tab') ?? '';
  const tab = (VALID_TABS as readonly string[]).includes(raw) ? raw : 'account';
  const setTab = (next: string) => setSearchParams({ tab: next }, { replace: true });

  return (
    <PageWrap>
      <PageHeader
        title="Cài đặt"
        subtitle="Thông tin tài khoản, AI và tổ chức."
      />

      <PageSection>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="mb-6">
            <TabsTrigger value="account">Tài khoản</TabsTrigger>
            <TabsTrigger value="general">Chung</TabsTrigger>
          </TabsList>
          <TabsContent value="account">
            <AccountTab />
          </TabsContent>
          <TabsContent value="general">
            <GeneralTab />
          </TabsContent>
        </Tabs>
      </PageSection>
    </PageWrap>
  );
}
