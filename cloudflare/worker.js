const DEFAULT_UPSTREAM_API_ORIGIN = "https://stocks.mastersgo.cc";
const QUOTE_CACHE_SECONDS = 60;
const POLICY_CACHE_SECONDS = 300;

const SECURITY_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Content-Type-Options": "nosniff",
};

function applyHeaders(headers, extra = {}) {
  const output = new Headers(headers);
  for (const [key, value] of Object.entries(SECURITY_HEADERS)) output.set(key, value);
  for (const [key, value] of Object.entries(extra)) output.set(key, value);
  output.delete("set-cookie");
  return output;
}

function jsonResponse(payload, status = 200, cacheControl = "no-store") {
  return new Response(JSON.stringify(payload), {
    status,
    headers: applyHeaders(
      { "Content-Type": "application/json; charset=utf-8" },
      { "Cache-Control": cacheControl },
    ),
  });
}

export function parseCsvRows(text) {
  const rows = [];
  let row = [];
  let value = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (character === '"') {
      if (quoted && text[index + 1] === '"') {
        value += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === "," && !quoted) {
      row.push(value);
      value = "";
    } else if ((character === "\n" || character === "\r") && !quoted) {
      if (character === "\r" && text[index + 1] === "\n") index += 1;
      row.push(value);
      value = "";
      if (row.some((cell) => cell.length)) rows.push(row);
      row = [];
    } else {
      value += character;
    }
  }

  if (value.length || row.length) {
    row.push(value);
    if (row.some((cell) => cell.length)) rows.push(row);
  }
  if (!rows.length) return [];

  const headers = rows[0].map((header) => header.replace(/^\uFEFF/, "").trim());
  return rows.slice(1).map((cells) => Object.fromEntries(headers.map((header, index) => [header, cells[index] || ""])));
}

export function buildHealthPayload(poolRows) {
  const rows = poolRows.filter((row) => row.ticker);
  const markets = {};
  for (const row of rows) {
    const market = row.market || "美股";
    markets[market] = (markets[market] || 0) + 1;
  }
  return {
    ok: true,
    runtime: "cloudflare-workers",
    symbols: rows.length,
    markets,
    cacheSeconds: QUOTE_CACHE_SECONDS,
    policyEndpoint: "/api/policy",
  };
}

async function loadPool(request, env) {
  const assetUrl = new URL("/stock-pool.csv", request.url);
  const response = await env.ASSETS.fetch(new Request(assetUrl));
  if (!response.ok) throw new Error(`stock-pool.csv unavailable (${response.status})`);
  return parseCsvRows(await response.text());
}

function upstreamOrigin(request, env) {
  const configured = String(env.UPSTREAM_API_ORIGIN || DEFAULT_UPSTREAM_API_ORIGIN).trim();
  const origin = new URL(configured);
  if (!/^https?:$/.test(origin.protocol)) throw new Error("UPSTREAM_API_ORIGIN must use http or https");
  if (origin.origin === new URL(request.url).origin) throw new Error("UPSTREAM_API_ORIGIN cannot point to this Worker");
  return origin;
}

async function proxyApi(request, env, cacheSeconds) {
  const incoming = new URL(request.url);
  const target = new URL(`${incoming.pathname}${incoming.search}`, upstreamOrigin(request, env));
  const force = incoming.searchParams.get("refresh") === "1";
  const response = await fetch(target, {
    headers: {
      Accept: "application/json",
      "User-Agent": "AIStockPoolCloudflare/1.0",
    },
    cf: force ? { cacheTtl: 0 } : { cacheEverything: true, cacheTtl: cacheSeconds },
  });
  if (!response.ok) throw new Error(`upstream ${incoming.pathname} returned ${response.status}`);
  return new Response(response.body, {
    status: response.status,
    headers: applyHeaders(response.headers, {
      "Cache-Control": force
        ? "no-store"
        : `public, max-age=0, s-maxage=${cacheSeconds}, stale-while-revalidate=${cacheSeconds * 5}`,
    }),
  });
}

async function policyFallback(request, env, reason) {
  const assetUrl = new URL("/tpi-latest.json", request.url);
  const response = await env.ASSETS.fetch(new Request(assetUrl));
  if (!response.ok) {
    return jsonResponse({ status: "error", error: "政策压力数据暂时不可用", detail: reason }, 502);
  }
  const payload = await response.json();
  return jsonResponse(
    { ...payload, status: "fallback", warning: reason },
    200,
    `public, max-age=0, s-maxage=${POLICY_CACHE_SECONDS}`,
  );
}

async function quoteFallback(request, env, reason) {
  const rows = await loadPool(request, env);
  const health = buildHealthPayload(rows);
  return jsonResponse({
    asOf: new Date().toISOString(),
    source: "static fallback",
    refreshSeconds: QUOTE_CACHE_SECONDS,
    requested: health.symbols,
    received: 0,
    markets: health.markets,
    missing: rows.map((row) => row.ticker).filter(Boolean).sort(),
    quotes: {},
    stale: true,
    warning: reason,
  });
}

async function handleApi(request, env) {
  const { pathname } = new URL(request.url);
  if (pathname === "/api/health") {
    try {
      return jsonResponse(buildHealthPayload(await loadPool(request, env)));
    } catch (error) {
      return jsonResponse({ ok: false, error: String(error) }, 500);
    }
  }
  if (pathname === "/api/quotes") {
    try {
      return await proxyApi(request, env, QUOTE_CACHE_SECONDS);
    } catch (error) {
      return quoteFallback(request, env, String(error));
    }
  }
  if (pathname === "/api/policy") {
    try {
      return await proxyApi(request, env, POLICY_CACHE_SECONDS);
    } catch (error) {
      return policyFallback(request, env, String(error));
    }
  }
  return jsonResponse({ error: "Not found" }, 404);
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: applyHeaders({}) });
    }
    if (request.method !== "GET") return jsonResponse({ error: "Method not allowed" }, 405);

    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/")) return handleApi(request, env);
    return env.ASSETS.fetch(request);
  },
};
