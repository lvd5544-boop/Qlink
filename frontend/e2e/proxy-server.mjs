import http from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distDir = path.resolve(__dirname, '../dist');
const port = Number(process.env.E2E_PORT || 4173);
const apiTarget = process.env.E2E_API_ORIGIN || 'http://127.0.0.1:8000';

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.json': 'application/json',
  '.woff2': 'font/woff2',
};

function sendFile(res, filePath) {
  const ext = path.extname(filePath);
  res.writeHead(200, { 'Content-Type': mime[ext] || 'application/octet-stream' });
  createReadStream(filePath).pipe(res);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://127.0.0.1:${port}`);
  if (url.pathname.startsWith('/api/')) {
    const target = new URL(url.pathname.replace(/^\/api/, '') + url.search, apiTarget);
    const headers = { ...req.headers, host: target.host };
    delete headers['content-length'];
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks);
    try {
      const upstream = await fetch(target, {
        method: req.method,
        headers,
        body: ['GET', 'HEAD'].includes(req.method || 'GET') ? undefined : body,
      });
      const buf = Buffer.from(await upstream.arrayBuffer());
      const outHeaders = {};
      upstream.headers.forEach((value, key) => {
        if (key.toLowerCase() === 'transfer-encoding') return;
        outHeaders[key] = value;
      });
      res.writeHead(upstream.status, outHeaders);
      res.end(buf);
    } catch (err) {
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ detail: String(err) }));
    }
    return;
  }

  let filePath = path.join(distDir, url.pathname === '/' ? 'index.html' : url.pathname);
  if (!existsSync(filePath) || statSync(filePath).isDirectory()) {
    filePath = path.join(distDir, 'index.html');
  }
  sendFile(res, filePath);
});

server.listen(port, '127.0.0.1', () => {
  console.log(`e2e proxy listening on http://127.0.0.1:${port}`);
});
