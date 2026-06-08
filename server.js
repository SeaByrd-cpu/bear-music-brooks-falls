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

wss.on("connection", () => {
  console.log("🌐 Browser connected via WebSocket");
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