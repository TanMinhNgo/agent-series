import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type {
  Document,
  KnowledgeCollection,
  LibraryAsset,
  LibraryAssetPreview,
  LibraryAssetUpdate,
  LibraryMemory,
  WorkerStatus,
} from '@/src/types';

export function useLibraryData(args: {
  query: string;
  scope: 'all' | 'global' | 'project';
  projectId: string;
  collectionProjectId: string;
  previewId?: string;
  onUpload: (errors: { name: string; message: string }[]) => void;
  onCollectionCreated: () => void;
}) {
  const client = useQueryClient();
  const { query, scope, projectId, collectionProjectId, previewId, onUpload, onCollectionCreated } = args;
  const assets = useQuery({
    queryKey: ['library-assets', query, scope, projectId],
    queryFn: () =>
      request<LibraryAsset[]>({
        url: '/library/assets',
        params: { query, scope, ...(scope === 'project' ? { projectId } : {}) },
      }),
  });
  const memories = useQuery({
    queryKey: ['memories', query],
    queryFn: () => request<LibraryMemory[]>({ url: '/memories', params: { query } }),
  });
  const documents = useQuery({
    queryKey: ['documents'],
    queryFn: () => request<Document[]>({ url: '/documents' }),
    refetchInterval: (state) =>
      state.state.data?.some((item) => item.status === 'queued' || item.status === 'indexing') ? 1500 : false,
  });
  const worker = useQuery({
    queryKey: ['worker-status'],
    queryFn: () => request<WorkerStatus>({ url: '/worker/status' }),
    refetchInterval: 3000,
  });
  const collections = useQuery({
    queryKey: queryKeys.collections(collectionProjectId),
    queryFn: () => request<KnowledgeCollection[]>({ url: `/projects/${collectionProjectId}/collections` }),
    enabled: Boolean(collectionProjectId),
  });
  const preview = useQuery({
    queryKey: ['artifact-preview', previewId],
    queryFn: () => request<LibraryAssetPreview>({ url: `/library/assets/${previewId}/preview` }),
    enabled: Boolean(previewId),
  });
  const versions = useQuery({
    queryKey: ['artifact-versions', previewId],
    queryFn: () => request<LibraryAsset[]>({ url: `/library/assets/${previewId}/versions` }),
    enabled: Boolean(previewId),
  });
  const invalidateLibrary = () => void client.invalidateQueries({ queryKey: ['library-assets'] });
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      const data = new FormData();
      files.forEach((file) => data.append('files', file));
      if (scope === 'project' && projectId) data.append('projectId', projectId);
      return request<{ errors: { name: string; message: string }[] }>({
        url: '/library/assets',
        method: 'POST',
        data,
      });
    },
    onSuccess: (result) => {
      onUpload(result.errors);
      invalidateLibrary();
    },
  });
  const deleteAsset = useMutation({
    mutationFn: (id: string) => request<void>({ url: `/library/assets/${id}`, method: 'DELETE' }),
    onSuccess: invalidateLibrary,
  });
  const updateAsset = useMutation({
    mutationFn: ({ id, data }: { id: string; data: LibraryAssetUpdate }) =>
      request<LibraryAsset>({ url: `/library/assets/${id}`, method: 'PATCH', data }),
    onSuccess: invalidateLibrary,
  });
  const createVersion = useMutation({
    mutationFn: async ({ id, file }: { id: string; file: File }) => {
      const data = new FormData();
      data.append('file', file);
      return request<LibraryAsset>({ url: `/library/assets/${id}/versions`, method: 'POST', data });
    },
    onSuccess: () => {
      invalidateLibrary();
      void client.invalidateQueries({ queryKey: ['artifact-versions'] });
    },
  });
  const reindexArtifact = useMutation({
    mutationFn: (id: string) =>
      request<LibraryAsset>({ url: `/library/assets/${id}/reindex`, method: 'POST' }),
    onSuccess: invalidateLibrary,
  });
  const deleteMemory = useMutation({
    mutationFn: (id: string) => request<void>({ url: `/memories/${id}`, method: 'DELETE' }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['memories'] }),
  });
  const reindex = useMutation({
    mutationFn: (id: string) => request<Document>({ url: `/documents/${id}/reindex`, method: 'POST' }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['documents'] }),
  });
  const deleteDocument = useMutation({
    mutationFn: (id: string) => request<void>({ url: `/documents/${id}`, method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.documents });
      void client.invalidateQueries({ queryKey: queryKeys.collectionsRoot });
    },
  });
  const createCollection = useMutation({
    mutationFn: (name: string) =>
      request<KnowledgeCollection>({
        url: `/projects/${collectionProjectId}/collections`,
        method: 'POST',
        data: { name },
      }),
    onSuccess: () => {
      onCollectionCreated();
      void client.invalidateQueries({ queryKey: queryKeys.collectionsRoot });
    },
  });
  const saveCollectionDocuments = useMutation({
    mutationFn: ({ id, documentIds }: { id: string; documentIds: string[] }) =>
      request<KnowledgeCollection>({
        url: `/collections/${id}/documents`,
        method: 'PUT',
        data: { documentIds },
      }),
    onSuccess: () => void client.invalidateQueries({ queryKey: queryKeys.collectionsRoot }),
  });
  const deleteCollection = useMutation({
    mutationFn: (id: string) => request<void>({ url: `/collections/${id}`, method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.collectionsRoot });
      void client.invalidateQueries({ queryKey: queryKeys.chats });
    },
  });
  return {
    assets,
    memories,
    documents,
    worker,
    collections,
    preview,
    versions,
    upload,
    deleteAsset,
    updateAsset,
    createVersion,
    reindexArtifact,
    deleteMemory,
    reindex,
    deleteDocument,
    createCollection,
    saveCollectionDocuments,
    deleteCollection,
  };
}
