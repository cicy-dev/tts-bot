const http = require("http");
const httpProxy = require("http-proxy");
const { spawn } = require("child_process");
const Redis = require("ioredis");

const PORT = parseInt(process.env.ROUTER_PORT || "12345");
const AUTH_TOKEN = process.env.ROUTER_TOKEN || "pb200898";
const TMUX_SOCKET = process.env.TMUX_SOCKET || `/tmp/tmux-${process.getuid()}/default`;
const REDIS_KEY = "tts:session_map";

let nextPort = 13000;
const instances = {}; // bot_name → { proc, port, winId }
const redis = new Redis();
const proxy = httpProxy.createProxyServer({ ws: true });

proxy.on("error", (err, req, res) => {
  console.error("proxy error:", err.message);
  if (res.writeHead) res.writeHead(502).end("Bad Gateway");
});

// --- session_map ---
async function findBot(botName) {
  const all = await redis.hgetall(REDIS_KEY);
  for (const [wid, json] of Object.entries(all)) {
    try {
      const info = JSON.parse(json);
      if (info.bot_name === botName) return { winId: wid, ...info };
    } catch {}
  }
  return null;
}

// --- ttyd 管理 ---
function startTtyd(botName, winId) {
  const existing = instances[botName];
  if (existing && !existing.proc.killed && existing.proc.exitCode === null) {
    return existing.port;
  }
  const port = nextPort++;
  const proc = spawn("ttyd", [
    "-p", String(port), "-W", "-i", "127.0.0.1",
    "-b", `/${botName}`,
    "tmux", "-S", TMUX_SOCKET, "attach-session", "-t", winId,
  ], { stdio: "ignore" });
  proc.on("exit", () => console.log(`ttyd ${botName} exited`));
  instances[botName] = { proc, port, winId };
  console.log(`🚀 ttyd /${botName} → :${port} → ${winId} (pid=${proc.pid})`);
  return port;
}

// --- 请求处理 ---
async function handleRequest(req, res) {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const parts = url.pathname.split("/").filter(Boolean);
  const botName = parts[0];

  if (!botName) {
    // 首页
    const all = await redis.hgetall(REDIS_KEY);
    const links = Object.values(all).map((j) => {
      try { const b = JSON.parse(j); return b.bot_name ? `<li><a href="/${b.bot_name}/?token=${AUTH_TOKEN}">${b.bot_name}</a></li>` : ""; } catch { return ""; }
    }).join("");
    res.writeHead(200, { "content-type": "text/html" });
    return res.end(`<h3>Bot Router</h3><ul>${links}</ul>`);
  }

  // token 验证
  const token = url.searchParams.get("token");
  const hasInstance = instances[botName]?.proc?.exitCode === null;
  if (token !== AUTH_TOKEN && !hasInstance) {
    res.writeHead(403);
    return res.end("Forbidden");
  }

  const bot = await findBot(botName);
  if (!bot) { res.writeHead(404); return res.end("Bot not found"); }

  const port = startTtyd(botName, bot.winId);
  // 等 ttyd 首次启动
  if (!hasInstance) await new Promise((r) => setTimeout(r, 800));

  proxy.web(req, res, { target: `http://127.0.0.1:${port}` });
}

const server = http.createServer(handleRequest);

// WS upgrade — 同样的逻辑，proxy 自动处理
server.on("upgrade", async (req, socket, head) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const botName = url.pathname.split("/").filter(Boolean)[0];
  if (!botName) return socket.destroy();

  const token = url.searchParams.get("token");
  const hasInstance = instances[botName]?.proc?.exitCode === null;
  if (token !== AUTH_TOKEN && !hasInstance) return socket.destroy();

  const bot = await findBot(botName);
  if (!bot) return socket.destroy();

  const port = startTtyd(botName, bot.winId);
  proxy.ws(req, socket, head, { target: `http://127.0.0.1:${port}` });
});

server.listen(PORT, () => console.log(`🌐 Bot Router on :${PORT}`));

process.on("SIGTERM", () => {
  Object.values(instances).forEach((i) => i.proc.kill());
  process.exit(0);
});
