// Starts a real VS Code with this extension on a fixture project and runs suite.ts inside it.
// VS Code: $VSCODE_BIN, else the macOS app, else `code`. Python with pyxpo: $PYXPO_PYTHON, else the repo .venv.
import { spawnSync } from "child_process";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

const ext = path.resolve(__dirname, "..", "..", "..");
const repo = path.resolve(ext, "..", "..");

function vscodeBin(): string {
  if (process.env.VSCODE_BIN) return process.env.VSCODE_BIN;
  const mac = "/Applications/Visual Studio Code.app/Contents/MacOS/Code";
  if (fs.existsSync(mac)) return mac;
  const old = "/Applications/Visual Studio Code.app/Contents/MacOS/Electron";
  return fs.existsSync(old) ? old : "code";
}

const APP = `from pyxpo import Pressable, StyleSheet, Text, View


def Screen():
    return View(
        Pressable(Text("Go", style=styles.title), onPress=lambda: None),
        style={"backgroundColor": "rgba(0, 128, 255, 0.5)", "borderColor": "#0f08"},
    )


styles = StyleSheet.create({
    "box": {"justifyContent": "center", "flexDirection": "row", "backgroundColr": "#ff0000"},
    "bad": {"alignItems": "middle", "color": "#12345", "borderColor": "white"},
    "title": {},
})

label = "blue"
# snippets here

default = Screen
`;

// In the project but without a pyxpo import yet: auto-import has to start from nothing.
const SCREEN = `import os


def Home():
    n, set_n = useState(0)
    return Vi
`;

const PLAIN = `import os

View(style={})
`;

const TOML = `[project]
name = "demo"
version = "0.1.0"

[tool.pyxpo]
name = "demo"
scheme = "demo"
nmae = "x"
background_color = "#336699"
# keys here
`;

// With --vsix=<file> the packaged extension is installed like a user's and the tests load from a tiny harness
// extension instead: VS Code exempts the extension under development from workspace trust, so only an installed one
// shows what Restricted Mode does to it.
const vsix = process.argv.find((a) => a.startsWith("--vsix="))?.slice(7);

/** One VS Code run on a fresh copy of the fixture project; `trusted` false runs it in Restricted Mode. */
function runOnce(trusted: boolean): number {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "pyxpo-vscode-e2e-"));
  const ws = path.join(tmp, "demo");
  fs.mkdirSync(path.join(ws, ".vscode"), { recursive: true });
  fs.writeFileSync(path.join(ws, "app.py"), APP);
  fs.writeFileSync(path.join(ws, "plain.py"), PLAIN);
  fs.writeFileSync(path.join(ws, "screen.py"), SCREEN);
  fs.writeFileSync(path.join(ws, "pyproject.toml"), TOML);
  const py = process.env.PYXPO_PYTHON || path.join(repo, ".venv", "bin", "python");
  fs.writeFileSync(path.join(ws, ".vscode", "settings.json"), JSON.stringify({
    "pyxpo.pythonPath": py,
    "editor.wordBasedSuggestions": "off", // only this extension's items in completion lists
  }));

  fs.mkdirSync(path.join(tmp, "user", "User"), { recursive: true });
  fs.writeFileSync(path.join(tmp, "user", "User", "settings.json"), JSON.stringify({
    "security.workspace.trust.startupPrompt": "never", // no modal: the folder just opens in Restricted Mode
  }));

  const env: NodeJS.ProcessEnv = { ...process.env, PYXPO_E2E_TRUSTED: trusted ? "1" : "0" };
  delete env.ELECTRON_RUN_AS_NODE; // set when this runs from a VS Code terminal; it makes Code act as plain node
  let devPath = ext;
  if (vsix) {
    devPath = path.join(tmp, "harness");
    fs.mkdirSync(devPath);
    fs.writeFileSync(path.join(devPath, "package.json"), JSON.stringify({
      name: "pyxpo-e2e-harness", publisher: "pyxpo", version: "0.0.0", engines: { vscode: "*" },
    }));
    // the `code` CLI next to the app binary: the app binary itself would open a window
    const cli = process.env.VSCODE_CLI || path.join(path.dirname(vscodeBin()), "..", "Resources", "app", "bin", "code");
    const inst = spawnSync(fs.existsSync(cli) ? cli : "code", [`--extensions-dir=${path.join(tmp, "exts")}`,
      `--user-data-dir=${path.join(tmp, "user")}`, "--install-extension", path.resolve(vsix)], { env, encoding: "utf8" });
    if (inst.status !== 0) throw new Error(`installing ${vsix} failed: ${inst.stderr || inst.stdout}`);
  }
  const r = spawnSync(vscodeBin(), [
    ws,
    `--extensionDevelopmentPath=${devPath}`,
    `--extensionTestsPath=${path.join(__dirname, "suite.js")}`,
    `--user-data-dir=${path.join(tmp, "user")}`,
    `--extensions-dir=${path.join(tmp, "exts")}`,
    ...(trusted ? ["--disable-workspace-trust"] : []),
    "--skip-welcome",
    "--skip-release-notes",
    "--new-window",
  ], { env, stdio: "inherit" });
  fs.rmSync(tmp, { recursive: true, force: true });
  if (r.error) throw r.error;
  return r.status ?? 1;
}

const modes = process.argv.includes("--restricted-only") ? [false] : [true, false];
let failed = 0;
for (const trusted of modes) {
  console.log(`\n== ${trusted ? "trusted folder" : "Restricted Mode (untrusted folder)"} ==`);
  if (runOnce(trusted) !== 0) failed++;
}
process.exit(failed ? 1 : 0);
