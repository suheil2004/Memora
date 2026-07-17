export interface ChatSiteAdapter {
  readonly id: string;
  supports(location: Location): boolean;
  getCurrentUserQuery(): string | null;
  makeContextAvailable(context: string): Promise<void>;
}

