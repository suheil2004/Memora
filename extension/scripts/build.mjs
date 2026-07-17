import { build } from "esbuild";
import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const extensionRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const dist = join(extensionRoot, "dist");

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });
await build({
  absWorkingDir: extensionRoot,
  entryPoints: {
    background: join(extensionRoot, "src", "background.ts"),
    content: join(extensionRoot, "src", "content.ts"),
    popup: join(extensionRoot, "src", "popup.ts"),
  },
  bundle: true,
  format: "esm",
  target: "chrome120",
  outdir: dist,
  sourcemap: true,
});
await Promise.all([
  cp(join(extensionRoot, "manifest.json"), join(dist, "manifest.json")),
  cp(join(extensionRoot, "popup.html"), join(dist, "popup.html")),
  cp(join(extensionRoot, "popup.css"), join(dist, "popup.css")),
]);
