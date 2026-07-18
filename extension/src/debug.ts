const PREFIX = "[Memora Debug]";

export function debug(scope: "CONTENT" | "BACKGROUND", message: string, detail?: unknown): void {
  if (detail === undefined) console.debug(`${PREFIX} ${scope}: ${message}`);
  else console.debug(`${PREFIX} ${scope}: ${message}`, detail);
}
