// English dictionary — keys mirror vi.ts. Missing keys fall back to Vietnamese.
export const en: Record<string, string> = {
  // common
  'common.save': 'Save',
  'common.saving': 'Saving…',
  'common.loading': 'Loading…',
  'common.saved': 'Saved',
  'common.saveError': 'Failed to save.',
  'common.language': 'Language',

  // Settings page
  'settings.title': 'Settings',
  'settings.subtitle': 'Account, AI and organization info.',
  'settings.tab.account': 'Account',
  'settings.tab.general': 'General',

  // Account tab
  'settings.account.email': 'Email',
  'settings.account.role': 'Role',
  'settings.account.google': 'Google',
  'settings.account.googleLinked': 'Linked',
  'settings.account.googleUnlinked': 'Not linked',
  'settings.account.plan': 'Plan',
  'settings.account.planExpiry': '(expires {date})',
  'settings.account.costCap': 'Cost cap/day',
  'settings.account.displayName': 'Display name',
  'settings.account.displayNamePlaceholder': 'Enter display name',
  'settings.account.savedName': 'Display name saved.',

  // General section
  'settings.section.account': 'Account',
  'settings.section.general': 'General',
  'settings.general.displayName': 'Display name',
  'settings.general.displayNamePlaceholder': 'Display name',
  'settings.general.tz': 'Timezone',
  'settings.general.uiLanguage': 'Interface language',
  'settings.general.uiLanguageHint': 'Display language of the web app.',
  'settings.general.botLanguage': 'Assistant reply language',
  'settings.general.botLanguageHint': 'Language the bot uses when replying in chat/groups.',
  'settings.general.saved': 'General settings saved.',

  // language switcher
  'lang.vi': 'Tiếng Việt',
  'lang.en': 'English',
  'lang.auto': "Match sender's language",
};
