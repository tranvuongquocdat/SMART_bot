import { Button } from '@/components/ui/button';

export default function App() {
  return (
    <div className="min-h-screen p-8 space-y-4">
      <h1 className="text-2xl font-semibold">shadcn check</h1>
      <Button>Default</Button>
      <Button variant="outline">Outline</Button>
      <Button variant="ghost">Ghost</Button>
    </div>
  );
}
