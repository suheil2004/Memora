import type { ChatSiteAdapter } from "./chat-site-adapter";

/**
 * Placeholder for the MVP's one supported site. DOM access and automatic
 * injection are intentionally deferred until selectors and UX are specified.
 */
export class InitialSiteAdapter implements ChatSiteAdapter {
  readonly id = "initial-site";

  supports(_location: Location): boolean {
    return false;
  }

  getCurrentUserQuery(): string | null {
    return null;
  }

  async makeContextAvailable(_context: string): Promise<void> {
    throw new Error("Initial site adapter is not implemented yet.");
  }
}

