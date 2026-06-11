import { Cpu, Bot, UserCog, FileText, BarChart3, Code2, BookTemplate, Zap, GitBranch, CreditCard, Package, Plug2 } from 'lucide-react';
import type { NavSection } from '@/components/app-shell';

export const superadminNav: NavSection[] = [
  {
    label: 'AI & Agent',
    items: [
      { label: 'Models AI', href: '/app/superadmin/models', icon: Cpu },
      { label: 'Prompts', href: '/app/superadmin/prompts', icon: Code2 },
      { label: 'Agent triggers', href: '/app/superadmin/agent-triggers', icon: Zap },
      { label: 'Retrieval pipelines', href: '/app/superadmin/retrieval-pipelines', icon: GitBranch },
      { label: 'Note templates', href: '/app/superadmin/note-templates', icon: BookTemplate },
    ],
  },
  {
    label: 'Vận hành',
    items: [
      { label: 'Tài khoản bot', href: '/app/superadmin/bot-accounts', icon: Bot },
      { label: 'Boss', href: '/app/superadmin/bosses', icon: UserCog },
      { label: 'MCP Catalog', href: '/app/superadmin/mcp-catalog', icon: Plug2 },
    ],
  },
  {
    label: 'Kinh doanh',
    items: [
      { label: 'Gói dịch vụ', href: '/app/superadmin/plans', icon: Package },
      { label: 'Yêu cầu đăng ký', href: '/app/superadmin/subscriptions', icon: CreditCard },
    ],
  },
  {
    label: 'Giám sát',
    items: [
      { label: 'Sử dụng', href: '/app/superadmin/usage', icon: BarChart3 },
      { label: 'Audit log', href: '/app/superadmin/audit', icon: FileText },
    ],
  },
];
