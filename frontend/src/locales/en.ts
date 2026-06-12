// English dictionary — keys mirror vi.ts. Missing keys fall back to Vietnamese.
export const en: Record<string, string> = {
  // navigation — sections
  'nav.section.workspace': 'Workspace',
  'nav.section.account': 'Account',
  'nav.section.settings': 'Settings',
  'nav.section.aiAgent': 'AI & Agent',
  'nav.section.operations': 'Operations',
  'nav.section.business': 'Business',
  'nav.section.monitoring': 'Monitoring',
  // navigation — admin
  'nav.admin.dashboard': 'Overview',
  'nav.admin.chat': 'Assistant',
  'nav.admin.models': 'AI Models',
  'nav.admin.groups': 'Groups',
  'nav.admin.reminders': 'Reminders',
  'nav.admin.projects': 'Projects',
  'nav.admin.actionItems': 'Action items',
  'nav.admin.channels': 'Channels',
  'nav.admin.usage': 'Usage',
  'nav.admin.subscription': 'Subscription',
  'nav.admin.tools': 'Tools',
  'nav.admin.integrations': 'Integrations',
  'nav.admin.settings': 'Settings',
  // navigation — superadmin
  'nav.sa.models': 'AI Models',
  'nav.sa.prompts': 'Prompts',
  'nav.sa.agentTriggers': 'Agent triggers',
  'nav.sa.retrieval': 'Retrieval pipelines',
  'nav.sa.noteTemplates': 'Note templates',
  'nav.sa.botAccounts': 'Bot accounts',
  'nav.sa.bosses': 'Bosses',
  'nav.sa.proxies': 'Proxy',
  'nav.sa.mcpCatalog': 'MCP Catalog',
  'nav.sa.plans': 'Plans',
  'nav.sa.subscriptions': 'Subscription requests',
  'nav.sa.announcements': 'Announcements',
  'nav.sa.usage': 'Usage',
  'nav.sa.audit': 'Audit log',

  // common
  'common.save': 'Save',
  'common.saving': 'Saving…',
  'common.loading': 'Loading…',
  'common.saved': 'Saved',
  'common.saveError': 'Failed to save.',
  'common.language': 'Language',
  'common.search': 'Search',

  // command palette
  'cmd.placeholder': 'Search pages, actions…',
  'cmd.empty': 'No results.',
  'cmd.actions': 'Actions',
  'cmd.toggleTheme': 'Toggle light/dark',
  'cmd.logout': 'Log out',

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
