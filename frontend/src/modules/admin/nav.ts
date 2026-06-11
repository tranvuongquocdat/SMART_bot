import { LayoutDashboard, MessageCircle, Users, Bell, FolderKanban, ClipboardList, Link as LinkIcon, Settings, BarChart3, CreditCard, Wrench } from 'lucide-react';
import type { NavSection } from '@/components/app-shell';

export const adminNav: NavSection[] = [
  {
    label: 'Workspace',
    items: [
      { label: 'Tổng quan', href: '/app/admin/dashboard', icon: LayoutDashboard },
      { label: 'Trợ lý', href: '/app/admin/chat', icon: MessageCircle },
      { label: 'Nhóm', href: '/app/admin/groups', icon: Users },
      { label: 'Nhắc nhở', href: '/app/admin/reminders', icon: Bell },
      { label: 'Dự án', href: '/app/admin/projects', icon: FolderKanban },
      { label: 'Việc cần làm', href: '/app/admin/action-items', icon: ClipboardList },
    ],
  },
  {
    label: 'Tài khoản',
    items: [
      { label: 'Kênh kết nối', href: '/app/admin/channels', icon: LinkIcon },
      { label: 'Sử dụng', href: '/app/admin/usage', icon: BarChart3 },
      { label: 'Gói cước', href: '/app/admin/subscription', icon: CreditCard },
      { label: 'Tools', href: '/app/admin/tools', icon: Wrench },
    ],
  },
  {
    label: 'Cài đặt',
    items: [
      { label: 'Cài đặt', href: '/app/admin/settings', icon: Settings },
    ],
  },
];
