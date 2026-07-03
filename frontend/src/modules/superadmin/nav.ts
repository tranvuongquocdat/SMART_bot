import { Cpu, Bot, Scale, SlidersHorizontal, UserCog, FileText, BarChart3, Code2, BookTemplate, Zap, GitBranch, CreditCard, Package, Plug2, Network, Megaphone, Search } from 'lucide-react';
import type { NavSection } from '@/components/app-shell';

// label = khóa i18n (app-shell + command-palette render qua t()).
export const superadminNav: NavSection[] = [
  {
    label: 'nav.section.aiAgent',
    items: [
      { label: 'nav.sa.models', href: '/app/superadmin/models', icon: Cpu },
      { label: 'nav.sa.prompts', href: '/app/superadmin/prompts', icon: Code2 },
      { label: 'nav.sa.agentTriggers', href: '/app/superadmin/agent-triggers', icon: Zap },
      { label: 'nav.sa.retrieval', href: '/app/superadmin/retrieval-pipelines', icon: GitBranch },
      { label: 'nav.sa.noteTemplates', href: '/app/superadmin/note-templates', icon: BookTemplate },
    ],
  },
  {
    label: 'nav.section.operations',
    items: [
      { label: 'nav.sa.botAccounts', href: '/app/superadmin/bot-accounts', icon: Bot },
      { label: 'nav.sa.bosses', href: '/app/superadmin/bosses', icon: UserCog },
      { label: 'nav.sa.proxies', href: '/app/superadmin/proxies', icon: Network },
      { label: 'nav.sa.mcpCatalog', href: '/app/superadmin/mcp-catalog', icon: Plug2 },
      { label: 'nav.sa.integrations', href: '/app/superadmin/integrations', icon: Search },
      { label: 'nav.sa.platform', href: '/app/superadmin/platform', icon: SlidersHorizontal },
    ],
  },
  {
    label: 'nav.section.business',
    items: [
      { label: 'nav.sa.plans', href: '/app/superadmin/plans', icon: Package },
      { label: 'nav.sa.subscriptions', href: '/app/superadmin/subscriptions', icon: CreditCard },
      { label: 'nav.sa.legal', href: '/app/superadmin/legal', icon: Scale },
    ],
  },
  {
    label: 'nav.section.monitoring',
    items: [
      { label: 'nav.sa.announcements', href: '/app/superadmin/announcements', icon: Megaphone },
      { label: 'nav.sa.usage', href: '/app/superadmin/usage', icon: BarChart3 },
      { label: 'nav.sa.audit', href: '/app/superadmin/audit', icon: FileText },
    ],
  },
];
