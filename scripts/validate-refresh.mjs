import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const runDate = process.env.DISCOVERY_REPORT_DATE || new Date().toISOString().slice(0, 10);
const guardedFiles = {
  "discovery-signals.csv": 20,
  "discovery-candidates.csv": 20,
};

function rowCount(text) {
  return Math.max(0, text.trim().split(/\r?\n/).length - 1);
}

for (const [file, absoluteMinimum] of Object.entries(guardedFiles)) {
  const currentText = await readFile(resolve(root, file), "utf8");
  const currentRows = rowCount(currentText);
  if (currentRows < absoluteMinimum) {
    throw new Error(`${file} has only ${currentRows} rows; refusing to publish the refresh`);
  }

  try {
    const previousText = execFileSync("git", ["show", `HEAD:${file}`], { cwd: root, encoding: "utf8" });
    const previousRows = rowCount(previousText);
    const allowedMinimum = Math.max(absoluteMinimum, Math.floor(previousRows * 0.35));
    if (currentRows < allowedMinimum) {
      throw new Error(`${file} fell from ${previousRows} to ${currentRows} rows; refusing to publish the refresh`);
    }
  } catch (error) {
    if (error instanceof Error && error.message.includes("refusing to publish")) throw error;
    console.warn(`${file}: previous Git snapshot unavailable; skipped relative-size guard`);
  }

  console.log(`${file}: ${currentRows} rows passed refresh guards`);
}

const candidateText = await readFile(resolve(root, "discovery-candidates.csv"), "utf8");
if (!candidateText.split(/\r?\n/).slice(1).some((line) => line.startsWith(`${runDate},`))) {
  throw new Error(`discovery-candidates.csv does not contain run date ${runDate}`);
}

await readFile(resolve(root, "reports", `discovery-${runDate}.md`), "utf8");
console.log(`Refresh artifacts for ${runDate} are complete`);
