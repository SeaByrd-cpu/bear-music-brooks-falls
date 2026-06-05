// server.js
const express = require("express");
const path    = require("path");
const { spawn } = require("child_process");
const WebSocket  = require("ws");

const app       = express();
const HTTP_PORT = process.env.PORT || 3000;

app.use(express.static(path.join(__dirname, "public")));

const server = app.listen(HTTP_PORT, () => {
  console.log(`🐻 Website running at http://localhost:${HTTP_PORT}`);
});

const wss = new WebSocket.Server({ server });
console.log("🐻 WebSocket attached to same server");

function broadcast(msg) {
  wss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) client.send(msg);
  });
}

function startDetector() {
  console.log("🐍 Starting detector.py...");

  const detector = spawn("python3", ["detector.py"]);

  detector.stdout.on("data", (data) => {
    data.toString().split("\n").forEach((line) => {
      line = line.trim();
      if (line.startsWith("{")) {
        console.log("→", line);
        broadcast(line);
      }
    });
  });

  detector.stderr.on("data", (data) => {
    // detector.py logs its own status to stderr — just pass it through
    process.stderr.write(data);
  });

  detector.on("close", (code) => {
    console.log(`⚠️  detector.py exited (code ${code}) — restarting in 5s...`);
    setTimeout(startDetector, 5000);
  });
}

startDetector();
