// CarePath web app on Databricks Apps (Node.js runtime).
//
// Serves the built site from ./dist with no dependencies. Unknown paths such
// as /welcome and /sign-in get index.html, so the app's own router handles
// them (the "SPA fallback" a static host needs). Databricks tells the app
// which port to listen on through DATABRICKS_APP_PORT.
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const zlib = require("node:zlib");

const PORT = Number(process.env.DATABRICKS_APP_PORT || process.env.PORT || 8000);
const ROOT = path.join(__dirname, "dist");

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
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405, { Allow: "GET, HEAD" }).end();
    return;
  }
  if (req.url === "/healthz") {
    res.writeHead(200, { "Content-Type": "text/plain" }).end("ok");
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
  console.log(`CarePath web listening on :${PORT}`);
});
