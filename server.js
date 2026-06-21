const express = require("express");
const path = require("path");
const WebSocket = require("ws");

const app = express();
const HTTP_PORT = process.env.PORT || 3000;

app.use(express.json({ limit: "1mb" }));
app.use(express.static(path.join(__dirname, "public")));

const server = app.listen(HTTP_PORT, () => {
  console.log(`🐻 Website running on port ${HTTP_PORT}`);
});

const wss = new WebSocket.Server({ server });
console.log("🐻 WebSocket attached to same server");

// Heartbeat: detect dead connections that never get a clean close
// event (common with idle proxies/hosts) and terminate them instead
// of leaving the client thinking it's still connected to nothing.
function heartbeat() {
  this.isAlive = true;
}

wss.on("connection", (ws) => {
  console.log("🌐 Browser connected via WebSocket");

  ws.isAlive = true;
  ws.on("pong", heartbeat);

  ws.on("close", () => {
    console.log("🌐 Browser disconnected");
  });

  ws.on("error", (err) => {
    console.log("⚠️ WebSocket client error:", err.message);
  });
});

const pingInterval = setInterval(() => {
  wss.clients.forEach((ws) => {
    if (ws.isAlive === false) {
      console.log("🔌 Terminating unresponsive client");
      return ws.terminate();
    }

    ws.isAlive = false;
    ws.ping();
  });
}, 20000);

wss.on("close", () => {
  clearInterval(pingInterval);
});

function broadcast(msg) {

  console.log(
    "Broadcasting to",
    wss.clients.size,
    "clients"
  );

  wss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(msg);
    }
  });
}

// Local detector sends bear JSON here
app.post("/ingest", (req, res) => {
  const payload = req.body;

  if (!payload || !payload.bears) {
    return res.status(400).json({ error: "Invalid payload" });
  }

  const msg = JSON.stringify(payload);

  console.log("→", msg);
  broadcast(msg);

  res.json({ ok: true });
});

// Lightweight endpoint for an external uptime pinger (e.g.
// UptimeRobot, cron-job.org) to hit every few minutes, so Render's
// free-tier idle spin-down never triggers. Self-pinging from inside
// the same process doesn't reliably prevent spin-down on Render —
// an external pinger hitting this URL does.
app.get("/health", (req, res) => {
  res.json({ ok: true, uptime: process.uptime() });
});