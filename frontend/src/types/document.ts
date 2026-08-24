export type Document = {
  id: string;
  name: string;
  status: string;
  pageCount: number | null;
  error: string | null;
  jobAttempts: number;
  jobMaxAttempts: number;
  jobError: string | null;
  projectId: string | null;
  url: string;
};
