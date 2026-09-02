export type LibraryAsset = {
  id: string;
  name: string;
  mimeType: string;
  sizeBytes: number;
  source: string;
  projectId: string | null;
  artifactId: string;
  version: number;
  isProjectSource: boolean;
  indexStatus: string;
  indexError: string | null;
  createdAt: string;
  url: string;
};

export type LibraryAssetUpdate = {
  name?: string;
  projectId?: string | null;
  isProjectSource?: boolean;
};

export type LibraryMemory = {
  id: string;
  chatId: string;
  chatTitle: string;
  role: string;
  content: string;
  createdAt: string;
};

export type WorkerStatus = {
  online: boolean;
  lastHeartbeatAt: string | null;
  currentJobType: string | null;
  queued: number;
  running: number;
  failed: number;
  lastError: string | null;
};

export type KnowledgeCollection = {
  id: string;
  projectId: string;
  name: string;
  description: string | null;
  documentIds: string[];
  createdAt: string;
  updatedAt: string;
};

export type LibraryAssetPreview = {
  kind: 'image' | 'pdf' | 'text' | 'unsupported';
  content?: string;
  truncated?: boolean;
};

export type LibraryAssetDiff = {
  baseAssetId: string;
  baseVersion: number;
  assetId: string;
  version: number;
  diff: string;
};
