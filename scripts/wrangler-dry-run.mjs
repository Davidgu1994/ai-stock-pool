import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const workDir = resolve(root, ".wrangler");
await mkdir(resolve(workDir, "logs"), { recursive: true });

const executable = resolve(root, "node_modules", ".bin", process.platform === "win32" ? "wrangler.cmd" : "wrangler");
const child = spawn(executable, ["deploy", "--dry-run", "--outdir", resolve(workDir, "dry-run")], {
  cwd: root,
  env: {
    ...process.env,
    WRANGLER_LOG_PATH: resolve(workDir, "logs", "wrangler.log"),
    WRANGLER_SEND_METRICS: "false",
  },
  stdio: "inherit",
});

const exitCode = await new Promise((resolveExit, reject) => {
  child.once("error", reject);
  child.once("exit", (code) => resolveExit(code ?? 1));
});
if (exitCode !== 0) process.exit(exitCode);
