import { Cpu, Bot, UserCog, FileText, BarChart3 } from 'lucide-react';
import type { NavSection } from '@/components/app-shell';

export const superadminNav: NavSection[] = [
  {
    label: 'Super-admin',
    items: [
      { label: 'Models', href: '/app/superadmin/models', icon: Cpu },
      { label: 'Bot accounts', href: '/app/superadmin/bot-accounts', icon: Bot },
      { label: 'Users', href: '/app/superadmin/users', icon: UserCog },
      { label: 'Audit log', href: '/app/superadmin/audit', icon: FileText },
      { label: 'Usage', href: '/app/superadmin/usage', icon: BarChart3 },
    ],
  },
];
