import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { useT } from '@/lib/i18n';
import AccountTab from './account-tab';
import GeneralTab from './general-tab';

export default function SettingsPage() {
  const t = useT();

  return (
    <PageWrap>
      <PageHeader title={t('settings.title')} subtitle={t('settings.subtitle')} />

      <PageSection>
        <h2 className="text-sm font-semibold mb-3">{t('settings.section.account')}</h2>
        <AccountTab />
      </PageSection>

      <PageSection>
        <h2 className="text-sm font-semibold mb-3">{t('settings.section.general')}</h2>
        <GeneralTab />
      </PageSection>
    </PageWrap>
  );
}
