export type Project = {
  id: string;
  name: string;
  description: string | null;
  status: string;
  createdAt: string;
  updatedAt: string;
};
export type Schedule = {
  id: string;
  title: string;
  startsAt: string;
  endsAt: string | null;
  notes: string | null;
  projectId: string | null;
  createdAt: string;
  updatedAt: string;
};
export type Plugin = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  enabled: boolean;
  config: Record<string, unknown> | null;
  createdAt: string;
  updatedAt: string;
};
