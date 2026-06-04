import { LayoutDashboard, Users, Bell, FolderKanban, ClipboardList, Link as LinkIcon, Settings } from 'lucide-react';
import type { NavSection } from '@/components/app-shell';

export const adminNav: NavSection[] = [
  {
    label: 'Workspace',
    items: [
      { label: 'Dashboard', href: '/app/admin/dashboard', icon: LayoutDashboard },
      { label: 'Groups', href: '/app/admin/groups', icon: Users },
      { label: 'Reminders', href: '/app/admin/reminders', icon: Bell },
      { label: 'Projects', href: '/app/admin/projects', icon: FolderKanban },
      { label: 'Action items', href: '/app/admin/action-items', icon: ClipboardList },
    ],
  },
  {
    label: 'Cài đặt',
    items: [
      { label: 'Channels', href: '/app/admin/channels', icon: LinkIcon },
      { label: 'Settings', href: '/app/admin/settings', icon: Settings },
    ],
  },
];
