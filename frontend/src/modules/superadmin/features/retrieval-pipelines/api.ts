import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type RetrievalPipeline = {
  feature: string;
  stages_json: unknown[];
  description: string | null;
  updated_at: string | null;
};

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export const retrievalPipelinesQuery = queryOptions({
  queryKey: ['superadmin', 'retrieval-pipelines'] as const,
  queryFn: () => api<RetrievalPipeline[]>('/api/v1/superadmin/retrieval-pipelines'),
});

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export async function patchRetrievalPipeline(
  feature: string,
  body: {
    stages_json?: unknown[] | null;
    description?: string | null;
  },
) {
  return api<{ feature: string; ok: boolean }>(
    `/api/v1/superadmin/retrieval-pipelines/${encodeURIComponent(feature)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(body),
    },
  );
}
