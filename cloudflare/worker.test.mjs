import assert from "node:assert/strict";
import test from "node:test";

import { buildHealthPayload, parseCsvRows } from "./worker.js";

test("parseCsvRows handles quoted commas and escaped quotes", () => {
  const rows = parseCsvRows('ticker,company,market\nNVDA,"NVIDIA, Inc.",美股\n000001.SZ,"平安""银行",A股\n');
  assert.deepEqual(rows, [
    { ticker: "NVDA", company: "NVIDIA, Inc.", market: "美股" },
    { ticker: "000001.SZ", company: '平安"银行', market: "A股" },
  ]);
});

test("buildHealthPayload counts the deploy snapshot", () => {
  const payload = buildHealthPayload([
    { ticker: "NVDA", market: "美股" },
    { ticker: "INTC", market: "美股" },
    { ticker: "000001.SZ", market: "A股" },
  ]);
  assert.equal(payload.ok, true);
  assert.equal(payload.runtime, "cloudflare-workers");
  assert.equal(payload.symbols, 3);
  assert.deepEqual(payload.markets, { 美股: 2, A股: 1 });
});
