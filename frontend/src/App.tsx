import { BrowserRouter } from 'react-router-dom';
import { AppShell } from './components/app-shell';
import type { NavSection } from './components/app-shell';
import { LayoutDashboard, Users } from 'lucide-react';

const nav: NavSection[] = [
  {
    label: 'Workspace',
    items: [
      { label: 'Dashboard', href: '/app/admin/dashboard', icon: LayoutDashboard },
      { label: 'Groups', href: '/app/admin/groups', icon: Users },
    ],
  },
];

export default function App() {
  return (
    <BrowserRouter>
      <AppShell
        nav={nav}
        me={{ id: 1, roles: ['boss'] }}
        breadcrumb={<><span>Groups</span> <span className="text-[hsl(var(--dim))]">/</span> <b className="text-foreground font-medium">Phòng Kinh Doanh</b></>}
      >
        <div className="p-10">
          <h1 className="text-2xl font-semibold tracking-tight">Smoke test</h1>
          <p className="text-muted-foreground mt-1">AppShell renders</p>
        </div>
      </AppShell>
    </BrowserRouter>
  );
}
