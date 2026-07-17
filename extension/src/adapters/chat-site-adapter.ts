export interface ChatSiteAdapter {
  readonly id: string;
  isSupportedPage(location?: Location): boolean;
  hasDraftInput(): boolean;
  getCurrentDraftQuery(): string | null;
  observeInputChanges(callback: (query: string | null) => void): () => void;
}
