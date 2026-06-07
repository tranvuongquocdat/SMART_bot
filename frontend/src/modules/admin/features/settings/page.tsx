import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import AccountTab from './account-tab';
import AiTab from './ai-tab';
import GeneralTab from './general-tab';

const VALID_TABS = ['account', 'ai', 'general'];

export default function SettingsPage() {
  const [searchParams] = useSearchParams();
  const initialTab = VALID_TABS.includes(searchParams.get('tab') ?? '') ? searchParams.get('tab')! : 'account';
  const [tab, setTab] = useState(initialTab);

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
            <TabsTrigger value="ai">AI</TabsTrigger>
            <TabsTrigger value="general">Chung</TabsTrigger>
          </TabsList>
          <TabsContent value="account">
            <AccountTab />
          </TabsContent>
          <TabsContent value="ai">
            <AiTab />
          </TabsContent>
          <TabsContent value="general">
            <GeneralTab />
          </TabsContent>
        </Tabs>
      </PageSection>
    </PageWrap>
  );
}
