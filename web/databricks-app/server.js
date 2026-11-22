// Annu on Databricks Apps (Node.js + Python in one app).
//
// - Serves the built site from ./dist with no dependencies. Unknown paths such
//   as /welcome and /sign-in get index.html, so the app's own router handles
//   them (the "SPA fallback" a static host needs).
// - Starts the Python recommender (backend/, FastAPI) on a private port and
//   forwards /api/* to it. The recommender reads the live Databricks tables at
//   start-up as the app's own service principal; until it is ready, /api
//   answers 503 with a plain message the UI shows.
// - Databricks tells the app which port to listen on via DATABRICKS_APP_PORT.
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const zlib = require("node:zlib");
const { spawn } = require("node:child_process");

const PORT = Number(process.env.DATABRICKS_APP_PORT || process.env.PORT || 8000);
const ROOT = path.join(__dirname, "dist");
const API_PORT = Number(process.env.ANNU_API_PORT || 8001);
const BACKEND_DIR = path.join(__dirname, "backend");
let apiReady = false;
let failedStarts = 0; // consecutive recommender starts that ended before it was ready

// ---- the Python recommender, kept running ----
function startBackend(attempt = 0) {
  if (!fs.existsSync(path.join(BACKEND_DIR, "main.py"))) {
    console.log("No backend/ folder: serving the site only");
    return;
  }
  const python = process.env.PYTHON || "python";
  const child = spawn(python, ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", String(API_PORT)], {
    cwd: BACKEND_DIR,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const log = (chunk) => {
    const text = chunk.toString();
    process.stdout.write(`[api] ${text}`);
    if (text.includes("Application startup complete")) {
      apiReady = true;
      failedStarts = 0;
      console.log("Recommender ready");
    }
  };
  child.stdout.on("data", log);
  child.stderr.on("data", log);
  child.on("exit", (code) => {
    if (!apiReady) failedStarts += 1;
    apiReady = false;
    const wait = Math.min(30, 2 ** attempt);
    console.log(`Recommender exited (${code}); restarting in ${wait}s`);
    setTimeout(() => startBackend(attempt + 1), wait * 1000);
  });
}

function proxyApi(req, res) {
  if (!apiReady) {
    res.writeHead(503, { "Content-Type": "application/json", "Retry-After": "5" });
    const message =
      failedStarts >= 2
        ? "Live hospital data is unavailable right now. In an emergency, call 108."
        : "Loading live hospital data. Try again in a few seconds.";
    res.end(JSON.stringify({ detail: { message } }));
    return;
  }
  const upstream = http.request(
    { host: "127.0.0.1", port: API_PORT, path: req.url, method: req.method, headers: { ...req.headers, host: `127.0.0.1:${API_PORT}` } },
    (answer) => {
      res.writeHead(answer.statusCode ?? 502, answer.headers);
      answer.pipe(res);
    },
  );
  upstream.on("error", () => {
    if (!res.headersSent) res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ detail: { message: "The recommender is restarting. Try again in a few seconds." } }));
  });
  req.pipe(upstream);
}

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".ico": "image/x-icon",
  ".json": "application/json; charset=utf-8",
  ".woff2": "font/woff2",
};
const COMPRESSIBLE = new Set([".html", ".js", ".css", ".svg", ".json"]);

function resolve(urlPath) {
  const clean = path.normalize(decodeURIComponent(urlPath.split("?")[0])).replace(/^(\.\.[/\\])+/, "");
  const file = path.join(ROOT, clean);
  if (!file.startsWith(ROOT)) return null; // no escaping the dist folder
  try {
    if (fs.statSync(file).isFile()) return file;
  } catch {
    /* not a file: fall through to the app */
  }
  return null;
}

const server = http.createServer((req, res) => {
  if (req.url.startsWith("/api/")) {
    proxyApi(req, res);
    return;
  }
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405, { Allow: "GET, HEAD" }).end();
    return;
  }
  if (req.url === "/healthz") {
    res.writeHead(200, { "Content-Type": "text/plain" }).end(apiReady ? "ok" : "ok (recommender loading)");
    return;
  }
  const file = resolve(req.url) ?? path.join(ROOT, "index.html");
  const ext = path.extname(file);
  const headers = {
    "Content-Type": TYPES[ext] ?? "application/octet-stream",
    // Hashed build assets never change; the page itself always revalidates.
    "Cache-Control": file.includes(`${path.sep}assets${path.sep}`)
      ? "public, max-age=31536000, immutable"
      : "no-cache",
    "X-Content-Type-Options": "nosniff",
  };
  const gzip = COMPRESSIBLE.has(ext) && /\bgzip\b/.test(req.headers["accept-encoding"] ?? "");
  if (gzip) headers["Content-Encoding"] = "gzip";
  res.writeHead(200, headers);
  if (req.method === "HEAD") {
    res.end();
    return;
  }
  const stream = fs.createReadStream(file);
  (gzip ? stream.pipe(zlib.createGzip()) : stream).pipe(res);
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Annu web listening on :${PORT}`);
  startBackend();
});
