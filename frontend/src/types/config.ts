export type ProviderStatus = { available: boolean; message: string | null; models: string[] };

export type Config = {
  providers: Record<string, string[]>;
  defaultProvider: string;
  defaultModel: string;
  providerStatus?: { ollama?: ProviderStatus };
};
