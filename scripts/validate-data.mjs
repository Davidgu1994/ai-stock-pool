import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const minimumRows = {
  "stock-pool.csv": 1,
  "discovery-signals.csv": 1,
  "discovery-candidates.csv": 1,
  "discovery-history.csv": 1,
};

for (const [file, minimum] of Object.entries(minimumRows)) {
  const text = await readFile(resolve(root, file), "utf8");
  const rows = text.trim().split(/\r?\n/).length - 1;
  if (rows < minimum) throw new Error(`${file} contains ${rows} data rows; refusing to build`);
  console.log(`${file}: ${rows} data rows`);
}

const paperText = await readFile(resolve(root, "arxiv-papers.csv"), "utf8");
console.log(`arxiv-papers.csv: ${Math.max(0, paperText.trim().split(/\r?\n/).length - 1)} data rows`);
