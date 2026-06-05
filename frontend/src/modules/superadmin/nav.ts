import { Cpu, Bot, UserCog, FileText, BarChart3, Code2, BookTemplate, Zap } from 'lucide-react';
import type { NavSection } from '@/components/app-shell';

export const superadminNav: NavSection[] = [
  {
    label: 'Super-admin',
    items: [
      { label: 'Models', href: '/app/superadmin/models', icon: Cpu },
      { label: 'Bot accounts', href: '/app/superadmin/bot-accounts', icon: Bot },
      { label: 'Bosses', href: '/app/superadmin/bosses', icon: UserCog },
      { label: 'Prompts', href: '/app/superadmin/prompts', icon: Code2 },
      { label: 'Note templates', href: '/app/superadmin/note-templates', icon: BookTemplate },
      { label: 'Agent triggers', href: '/app/superadmin/agent-triggers', icon: Zap },
      { label: 'Audit log', href: '/app/superadmin/audit', icon: FileText },
      { label: 'Usage', href: '/app/superadmin/usage', icon: BarChart3 },
    ],
  },
];
