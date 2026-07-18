import { build } from "esbuild";
import { cp, mkdir, readFile, readdir, rm } from "node:fs/promises";
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

const configuredToken = process.env.MEMORA_LOCAL_TOKEN ?? "";
for (const entry of await readdir(dist)) {
  if (!/\.(?:js|map|html|json|css)$/.test(entry)) continue;
  const content = await readFile(join(dist, entry), "utf8");
  if (/OPENAI_API_KEY|sk-proj-|sk-/.test(content)) {
    throw new Error(`Secret-like OpenAI credential pattern found in extension build file: ${entry}`);
  }
  if (configuredToken.length >= 16 && content.includes(configuredToken)) {
    throw new Error(`Configured Memora local token found in extension build file: ${entry}`);
  }
}
