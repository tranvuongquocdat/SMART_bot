import { LayoutDashboard, MessageCircle, Cpu, Users, Bell, FolderKanban, ClipboardList, Link as LinkIcon, Settings, BarChart3, CreditCard, Plug2, Gauge } from 'lucide-react';
import type { NavSection } from '@/components/app-shell';

// label = khóa i18n (app-shell + command-palette render qua t()).
export const adminNav: NavSection[] = [
  {
    label: 'nav.section.workspace',
    items: [
      { label: 'nav.admin.dashboard', href: '/app/admin/dashboard', icon: LayoutDashboard },
      { label: 'nav.admin.chat', href: '/app/admin/chat', icon: MessageCircle },
      { label: 'nav.admin.models', href: '/app/admin/ai', icon: Cpu },
      { label: 'nav.admin.groups', href: '/app/admin/groups', icon: Users },
      { label: 'nav.admin.reminders', href: '/app/admin/reminders', icon: Bell },
      { label: 'nav.admin.projects', href: '/app/admin/projects', icon: FolderKanban },
      { label: 'nav.admin.actionItems', href: '/app/admin/action-items', icon: ClipboardList },
      { label: 'nav.admin.performance', href: '/app/admin/performance', icon: Gauge },
    ],
  },
  {
    label: 'nav.section.account',
    items: [
      { label: 'nav.admin.channels', href: '/app/admin/channels', icon: LinkIcon },
      { label: 'nav.admin.usage', href: '/app/admin/usage', icon: BarChart3 },
      { label: 'nav.admin.subscription', href: '/app/admin/subscription', icon: CreditCard },
      { label: 'nav.admin.integrations', href: '/app/admin/integrations', icon: Plug2 },
    ],
  },
  {
    label: 'nav.section.settings',
    items: [
      { label: 'nav.admin.settings', href: '/app/admin/settings', icon: Settings },
    ],
  },
];
