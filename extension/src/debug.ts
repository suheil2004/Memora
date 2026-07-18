const PREFIX = "[Memora Debug]";

function isDebugEnabled(): boolean {
  return (globalThis as { __MEMORA_DEBUG__?: unknown }).__MEMORA_DEBUG__ === true;
}

export function debug(scope: "CONTENT" | "BACKGROUND", message: string, detail?: unknown): void {
  if (!isDebugEnabled()) return;
  if (detail === undefined) console.debug(`${PREFIX} ${scope}: ${message}`);
  else console.debug(`${PREFIX} ${scope}: ${message}`, detail);
}
