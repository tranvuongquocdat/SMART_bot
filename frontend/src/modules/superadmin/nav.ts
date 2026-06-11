import { Cpu, Bot, UserCog, FileText, BarChart3, Code2, BookTemplate, Zap, GitBranch, CreditCard, Package, Plug2 } from 'lucide-react';
import type { NavSection } from '@/components/app-shell';

export const superadminNav: NavSection[] = [
  {
    label: 'Hệ thống',
    items: [
      { label: 'Models AI', href: '/app/superadmin/models', icon: Cpu },
      { label: 'Tài khoản bot', href: '/app/superadmin/bot-accounts', icon: Bot },
      { label: 'Boss', href: '/app/superadmin/bosses', icon: UserCog },
      { label: 'Prompts', href: '/app/superadmin/prompts', icon: Code2 },
      { label: 'Note templates', href: '/app/superadmin/note-templates', icon: BookTemplate },
      { label: 'Agent triggers', href: '/app/superadmin/agent-triggers', icon: Zap },
      { label: 'Audit log', href: '/app/superadmin/audit', icon: FileText },
      { label: 'Retrieval pipelines', href: '/app/superadmin/retrieval-pipelines', icon: GitBranch },
      { label: 'Sử dụng', href: '/app/superadmin/usage', icon: BarChart3 },
      { label: 'Yêu cầu đăng ký', href: '/app/superadmin/subscriptions', icon: CreditCard },
      { label: 'Gói dịch vụ', href: '/app/superadmin/plans', icon: Package },
      { label: 'MCP Catalog', href: '/app/superadmin/mcp-catalog', icon: Plug2 },
    ],
  },
];
