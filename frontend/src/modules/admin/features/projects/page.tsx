import { useState } from 'react';
import { useSuspenseQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { FolderKanban, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { EmptyState } from '@/components/empty-state';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { CreateProjectDialog } from './create-dialog';
import { projectsQuery, deleteProject, type Project } from './api';

function ProjectRow({ project }: { project: Project }) {
  const qc = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const deleteMut = useMutation({
    mutationFn: () => deleteProject(project.id),
    onSuccess: () => {
      qc.invalidateQueries(projectsQuery());
      toast.success('Đã xoá dự án');
      setConfirmDelete(false);
    },
    onError: () => toast.error('Xoá dự án thất bại'),
  });

  return (
    <>
      <tr className="border-t hover:bg-muted/30 transition-colors">
        <td className="p-3 font-medium">{project.name}</td>
        <td className="p-3 text-sm text-muted-foreground">{project.description ?? '—'}</td>
        <td className="p-3 text-center tabular-nums">{project.items_count}</td>
        <td className="p-3 text-right">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-destructive hover:text-destructive"
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2 className="h-4 w-4" />
            <span className="sr-only">Xoá</span>
          </Button>
        </td>
      </tr>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Xác nhận xoá dự án</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground mt-1">
            Dự án "{project.name}" sẽ bị xoá. Các việc cần làm thuộc dự án này sẽ không bị xoá.
          </p>
          <DialogFooter className="mt-4">
            <Button
              variant="outline"
              onClick={() => setConfirmDelete(false)}
              disabled={deleteMut.isPending}
            >
              Huỷ
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteMut.mutate()}
              disabled={deleteMut.isPending}
            >
              {deleteMut.isPending ? 'Đang xoá...' : 'Xoá'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function ProjectList() {
  const { data: projects } = useSuspenseQuery(projectsQuery());

  if (projects.length === 0) {
    return (
      <EmptyState
        icon={FolderKanban}
        title="Chưa có dự án nào"
        description="Tạo dự án để nhóm các việc cần làm lại với nhau."
      />
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-muted-foreground border-b">
          <th className="p-3">Tên dự án</th>
          <th className="p-3">Mô tả</th>
          <th className="p-3 text-center">Số việc</th>
          <th className="p-3 w-12"></th>
        </tr>
      </thead>
      <tbody>
        {projects.map(p => (
          <ProjectRow key={p.id} project={p} />
        ))}
      </tbody>
    </table>
  );
}

export default function ProjectsPage() {
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <PageWrap>
      <PageHeader
        title="Dự án"
        subtitle="Quản lý các dự án và nhóm việc cần làm"
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            Tạo dự án
          </Button>
        }
      />

      <PageSection className="rounded-[12px] bg-card-grad surface-section overflow-hidden">
        <ProjectList />
      </PageSection>

      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />
    </PageWrap>
  );
}
