import { useParams, type LoaderFunction } from 'react-router-dom';
import type { QueryClient } from '@tanstack/react-query';

export const groupDetailLoader = (_qc: QueryClient): LoaderFunction => async ({ params }) => {
  return { groupId: params.groupId };
};

export default function GroupDetail() {
  const params = useParams();
  return (
    <div className="p-10">
      <h1 className="text-2xl font-semibold tracking-tight">Group {params.groupId}</h1>
    </div>
  );
}
