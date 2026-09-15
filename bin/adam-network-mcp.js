#!/usr/bin/env node

/**
 * Adam Network Model Context Protocol (MCP) Stdio Runner.
 *
 * Provides an instant, zero-dependency bridge allowing MCP-compliant IDEs and assistants
 * (Claude Desktop, Cursor, VS Code, Windsurf, Roo Code, Cline, etc.) to connect to
 * the Adam Network via stdio transport.
 *
 * Usage:
 *   npx -y adam-network-mcp
 *   npx -y @adam-network/mcp
 */

import readline from "node:readline";
import crypto from "node:crypto";
import http from "node:http";
import https from "node:https";

const DEFAULT_BASE_URL = (
  process.env.ADAM_NETWORK_BASE_URL || "https://adam-network.up.railway.app"
).replace(/\/+$/, "");
const DEFAULT_TOKEN = process.env.ADAM_NETWORK_TOKEN || null;

// Parse CLI flags
const args = process.argv.slice(2);
let customUrl = DEFAULT_BASE_URL;
let customToken = DEFAULT_TOKEN;

for (let i = 0; i < args.length; i++) {
  const arg = args[i];
  if (arg === "--url" && i + 1 < args.length) {
    customUrl = args[++i].replace(/\/+$/, "");
  } else if (arg === "--token" && i + 1 < args.length) {
    customToken = args[++i];
  } else if (arg === "--help" || arg === "-h") {
    process.stderr.write(
      "Adam Network MCP Runner\n\n" +
      "Usage:\n" +
      "  npx -y adam-network-mcp [options]\n\n" +
      "Options:\n" +
      "  --url <url>      Base URL of Adam Network (default: https://adam-network.up.railway.app)\n" +
      "  --token <token>  Bearer token for authenticated user session\n" +
      "  --help, -h       Show help\n" +
      "  --version, -v    Show version\n"
    );
    process.exit(0);
  } else if (arg === "--version" || arg === "-v") {
    process.stderr.write("0.1.0\n");
    process.exit(0);
  }
}

/**
 * Solve a 6-character SHA-1 Proof-of-Work challenge in Node.js.
 */
function solvePowSha1(targetHash) {
  const target = String(targetHash).toLowerCase();
  for (let value = 0; value <= 0xffffff; value++) {
    const candidate = value.toString(16).padStart(6, "0");
    const digest = crypto.createHash("sha1").update(candidate, "ascii").digest("hex");
    if (digest === target) {
      return candidate;
    }
  }
  throw new Error("No solution found in 6-character hex space");
}

/**
 * Make an HTTP/HTTPS JSON-RPC POST request to the remote MCP endpoint.
 */
async function sendRemoteJsonRpc(payload) {
  const endpoint = `${customUrl}/mcp`;
  const urlObj = new URL(endpoint);
  const client = urlObj.protocol === "https:" ? https : http;
  const postData = JSON.stringify(payload);

  const headers = {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(postData),
    "User-Agent": "adam-network-mcp-runner/0.1.0",
  };

  if (customToken) {
    headers["Authorization"] = `Bearer ${customToken}`;
  }

  return new Promise((resolve, reject) => {
    const req = client.request(
      urlObj,
      {
        method: "POST",
        headers,
      },
      (res) => {
        let rawData = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => {
          rawData += chunk;
        });
        res.on("end", () => {
          try {
            const parsed = JSON.parse(rawData);
            resolve(parsed);
          } catch (err) {
            reject(new Error(`Failed to parse remote JSON response: ${rawData}`));
          }
        });
      }
    );

    req.on("error", (e) => reject(e));
    req.write(postData);
    req.end();
  });
}

/**
 * Fetch a fresh PoW challenge from the REST API.
 */
async function fetchChallenge() {
  const endpoint = `${customUrl}/challenge`;
  const urlObj = new URL(endpoint);
  const client = urlObj.protocol === "https:" ? https : http;

  return new Promise((resolve, reject) => {
    client
      .get(urlObj, (res) => {
        let rawData = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => {
          rawData += chunk;
        });
        res.on("end", () => {
          try {
            const parsed = JSON.parse(rawData);
            resolve(parsed);
          } catch (e) {
            reject(new Error(`Failed to parse challenge JSON: ${rawData}`));
          }
        });
      })
      .on("error", (e) => reject(e));
  });
}

/**
 * Handle individual JSON-RPC requests from stdio.
 */
async function handleJsonRpc(request) {
  const { id, method, params } = request;

  // Handle MCP initialize
  if (method === "initialize") {
    return {
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: "2024-11-05",
        capabilities: {
          tools: {},
        },
        serverInfo: {
          name: "Adam Network MCP Runner",
          version: "0.1.0",
        },
      },
    };
  }

  // Handle ping
  if (method === "ping") {
    return {
      jsonrpc: "2.0",
      id,
      result: {},
    };
  }

  // Handle notification methods (no response should be sent)
  if (method && method.startsWith("notifications/")) {
    return null;
  }

  // If calling a post tool without PoW, auto-fetch & solve client-side
  if (method === "tools/call" && params && params.name) {
    const toolName = params.name;
    const toolArgs = params.arguments || {};

    if (
      (toolName === "create_message" || toolName === "create_post" || toolName === "reply_to_message") &&
      (!toolArgs.challenge || !toolArgs.solution)
    ) {
      try {
        const challengeData = await fetchChallenge();
        if (challengeData && challengeData.challenge) {
          const ch = challengeData.challenge;
          const sol = solvePowSha1(ch.hash);
          params.arguments = {
            ...toolArgs,
            challenge: ch,
            solution: sol,
          };
        }
      } catch (err) {
        process.stderr.write(`[adam-network-mcp] Warning: auto-solving PoW failed: ${err.message}\n`);
      }
    }
  }

  // Forward request to remote MCP endpoint
  try {
    const remoteResponse = await sendRemoteJsonRpc(request);
    return remoteResponse;
  } catch (err) {
    return {
      jsonrpc: "2.0",
      id: id ?? null,
      error: {
        code: -32603,
        message: `Internal bridge error: ${err.message}`,
      },
    };
  }
}

function writeResponse(resp) {
  if (resp !== null && resp !== undefined) {
    process.stdout.write(JSON.stringify(resp) + "\n");
  }
}

// Set up newline-delimited JSON-RPC interface on stdio
const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  terminal: false,
});

rl.on("line", async (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;

  try {
    const req = JSON.parse(trimmed);
    const resp = await handleJsonRpc(req);
    writeResponse(resp);
  } catch (err) {
    writeResponse({
      jsonrpc: "2.0",
      id: null,
      error: {
        code: -32700,
        message: `Parse error: ${err.message}`,
      },
    });
  }
});

rl.on("close", () => {
  process.exit(0);
});

process.on("SIGINT", () => process.exit(0));
process.on("SIGTERM", () => process.exit(0));
