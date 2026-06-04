import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import AccountTab from './account-tab';
import AiTab from './ai-tab';
import GeneralTab from './general-tab';

export default function SettingsPage() {
  const [tab, setTab] = useState('account');

  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1100px]">
      <header className="mb-6">
        <h1 className="text-[24px] font-semibold tracking-tight">Cai dat</h1>
        <p className="text-muted-foreground mt-1.5">Thong tin tai khoan, AI va to chuc.</p>
      </header>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-6">
          <TabsTrigger value="account">Tai khoan</TabsTrigger>
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
    </div>
  );
}
