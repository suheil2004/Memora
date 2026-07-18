export interface ChatSiteAdapter {
  readonly id: string;
  isSupportedPage(location?: Location): boolean;
  hasDraftInput(): boolean;
  getCurrentDraftQuery(): string | null;
  setDraftQuery(text: string): boolean;
  observeInputChanges(callback: (query: string | null) => void): () => void;
}
