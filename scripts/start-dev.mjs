import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const frontend = path.join(root, "frontend");
const syncLimit = Number.parseInt(process.env.SYNC_LIMIT ?? "50", 10);
const children = [];

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function reachable(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(2000) });
    return response.ok;
  } catch {
    return false;
  }
}

async function waitFor(url, label, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await reachable(url)) return;
    await sleep(1000);
  }
  throw new Error(`${label} did not become ready within ${timeoutMs / 1000} seconds`);
}

function launch(command, args, cwd, label) {
  console.log(`[startup] Starting ${label}...`);
  const child = spawn(command, args, {
    cwd,
    stdio: "inherit",
    windowsHide: true,
    shell: false,
  });
  children.push(child);
  child.on("exit", code => {
    if (code && code !== 0) console.error(`[startup] ${label} exited with code ${code}`);
  });
  return child;
}

async function ensureServices() {
  const tasks = [];

  if (!(await reachable("http://127.0.0.1:11434/api/tags"))) {
    launch("ollama", ["serve"], root, "Ollama");
    tasks.push(waitFor("http://127.0.0.1:11434/api/tags", "Ollama"));
  } else {
    console.log("[startup] Reusing Ollama already running on port 11434.");
  }

  if (!(await reachable("http://127.0.0.1:8000/api/health"))) {
    launch("uv", ["run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], root, "FastAPI backend");
    tasks.push(waitFor("http://127.0.0.1:8000/api/health", "FastAPI backend"));
  } else {
    console.log("[startup] Reusing backend already running on port 8000.");
  }

  if (!(await reachable("http://127.0.0.1:5173"))) {
    if (process.platform === "win32") {
      const commandProcessor = process.env.ComSpec ?? "C:\\Windows\\System32\\cmd.exe";
      launch(
        commandProcessor,
        ["/d", "/s", "/c", "npm run dev -- --host 127.0.0.1"],
        frontend,
        "React frontend",
      );
    } else {
      launch("npm", ["run", "dev", "--", "--host", "127.0.0.1"], frontend, "React frontend");
    }
    tasks.push(waitFor("http://127.0.0.1:5173", "React frontend"));
  } else {
    console.log("[startup] Reusing frontend already running on port 5173.");
  }

  await Promise.all(tasks);
}

async function syncGmail() {
  const accountsResponse = await fetch("http://127.0.0.1:8000/api/accounts");
  if (!accountsResponse.ok) throw new Error(`Could not list Gmail accounts (${accountsResponse.status})`);
  const accounts = await accountsResponse.json();
  if (!accounts.length) {
    console.warn("[sync] No Gmail account is connected. Complete /api/auth/google/start first.");
    return;
  }

  console.log(`[sync] Fetching and classifying up to ${syncLimit} unseen matching emails...`);
  const response = await fetch(
    `http://127.0.0.1:8000/api/accounts/${accounts[0].id}/sync?limit=${syncLimit}`,
    { method: "POST" },
  );
  const body = await response.text();
  if (!response.ok) throw new Error(`Gmail sync failed (${response.status}): ${body}`);
  const result = JSON.parse(body);
  console.log(`[sync] Complete: ${result.created} new, ${result.duplicates} duplicates, ${result.scanned} scanned.`);
  console.log("[ready] Dashboard: http://127.0.0.1:5173");
}

function shutdown() {
  for (const child of children) {
    if (child.killed || !child.pid) continue;
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
        stdio: "ignore",
        windowsHide: true,
      });
    } else {
      child.kill("SIGTERM");
    }
  }
}

process.once("SIGINT", () => {
  shutdown();
  process.exit(0);
});
process.once("SIGTERM", () => {
  shutdown();
  process.exit(0);
});
process.once("exit", shutdown);

try {
  if (!Number.isInteger(syncLimit) || syncLimit < 1 || syncLimit > 500) {
    throw new Error("SYNC_LIMIT must be an integer from 1 to 500");
  }
  await ensureServices();
  try {
    await syncGmail();
  } catch (error) {
    console.error(`[sync] ${error instanceof Error ? error.message : error}`);
    console.log("[ready] Services remain running; retry the sync from the API or restart later.");
    console.log("[ready] Dashboard: http://127.0.0.1:5173");
  }
} catch (error) {
  console.error(`[startup] ${error instanceof Error ? error.message : error}`);
  shutdown();
  process.exitCode = 1;
}
