/**
 * Process bridge to `vscode_bridge.py`.
 *
 * All the analysis lives in the Python tool. This module only:
 *   1. finds the interpreter and the script,
 *   2. runs one of its JSON subcommands,
 *   3. turns a failure into a message a user can act on.
 *
 * Keeping the split here means the extension, the MCP server and the desktop
 * GUI can never disagree about what a defect's disposition is — there is one
 * implementation of the engine, and it is not TypeScript.
 */

import * as childProcess from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

// --------------------------------------------------------------------------- //
// Payload types (mirror SCHEMA_VERSION 1 of vscode_bridge.py)
// --------------------------------------------------------------------------- //
export type Disposition = 'Bug' | 'False positive' | 'Intentional' | 'Needs review';

export interface SourceContext {
  start_line: number;
  code: string;
  focus_line: number;
}

export interface CoverityEvent {
  step?: number;
  type?: string;
  description?: string;
  file?: string;
  line?: number;
  main?: boolean;
}

export interface DefectRecord {
  cid: number;
  checker: string;
  category: string;
  type: string;
  severity: string;
  file: string;
  resolved_file: string;
  line: number;
  line_is_various: boolean;
  function: string;
  disposition: Disposition | string;
  confidence: number;
  comment: string;
  proposed_fix: string;
  events?: CoverityEvent[];
  source_context?: SourceContext;
}

export interface DefectSummary {
  total: number;
  bug: number;
  false_positive: number;
  intentional: number;
  needs_review: number;
  mean_confidence: number;
  by_checker: Record<string, number>;
  by_severity: Record<string, number>;
}

export interface BackendInfo {
  key: string;
  label: string;
  available: boolean;
  detail: string;
  critical: boolean;
}

export interface CapabilitiesPayload {
  depth: 'full' | 'partial' | 'minimal' | string;
  backends: BackendInfo[];
  missing: string[];
  banner: string;
  recommendation?: string;
}

export interface AnalyzePayload {
  report: string;
  src_root: string;
  language: string;
  total_in_report: number;
  capabilities: CapabilitiesPayload;
  summary: DefectSummary;
  defects: DefectRecord[];
  written_to?: string;
}

export interface ListPayload {
  report: string;
  total_in_report: number;
  returned: number;
  defects: Array<Pick<DefectRecord, 'cid' | 'checker' | 'type' | 'severity' | 'file' | 'line' | 'line_is_various' | 'function'>>;
}

export interface AnnotationFile {
  schema: number;
  tool: string;
  generated_at: string;
  report: string;
  src_root: string;
  language: string;
  capabilities: CapabilitiesPayload;
  summary: DefectSummary;
  defects: DefectRecord[];
}

// --------------------------------------------------------------------------- //
// Errors
// --------------------------------------------------------------------------- //
export class BridgeError extends Error {
  constructor(message: string, public readonly hint?: string) {
    super(message);
    this.name = 'BridgeError';
  }

  /** Message + hint, formatted for a notification or a tool result. */
  toText(): string {
    return this.hint ? `${this.message}\n\n${this.hint}` : this.message;
  }
}

export function isCancellation(err: unknown): boolean {
  return err instanceof vscode.CancellationError ||
    (err instanceof Error && err.name === 'CancellationError');
}

// --------------------------------------------------------------------------- //
// Locating python + the bridge script
// --------------------------------------------------------------------------- //
export interface BridgeLocation {
  python: string;
  bridge: string;
  cwd: string;
}

const BRIDGE_FILE = 'vscode_bridge.py';

function firstExisting(candidates: string[]): string {
  for (const candidate of candidates) {
    if (!candidate) {
      continue;
    }
    try {
      if (fs.existsSync(candidate)) {
        return candidate;
      }
    } catch {
      // Unreadable path: keep looking.
    }
  }
  return '';
}

/**
 * Bridge script resolution order:
 *   1. `coverityTool.bridgePath`
 *   2. `<workspace>/Coverity-Tool/vscode_bridge.py`   (this repo's layout)
 *   3. `<workspace>/vscode_bridge.py`                 (flat checkout)
 *   4. `<extension>/../vscode_bridge.py`              (extension inside the repo)
 *   5. `<extension>/python/vscode_bridge.py`          (a bundled copy)
 */
export function locateBridge(context: vscode.ExtensionContext): BridgeLocation {
  const config = vscode.workspace.getConfiguration('coverityTool');
  const configuredScript = (config.get<string>('bridgePath') || '').trim();
  const workspaceFolders = vscode.workspace.workspaceFolders ?? [];

  const scriptCandidates: string[] = [];
  if (configuredScript) {
    scriptCandidates.push(...workspaceFolders.map(f => path.join(f.uri.fsPath, configuredScript)));
    scriptCandidates.push(configuredScript);
  }
  for (const folder of workspaceFolders) {
    scriptCandidates.push(path.join(folder.uri.fsPath, 'Coverity-Tool', BRIDGE_FILE));
    scriptCandidates.push(path.join(folder.uri.fsPath, BRIDGE_FILE));
  }
  scriptCandidates.push(path.join(context.extensionPath, '..', BRIDGE_FILE));
  scriptCandidates.push(path.join(context.extensionPath, 'python', BRIDGE_FILE));
  scriptCandidates.push(path.join(context.extensionPath, BRIDGE_FILE));

  const bridge = firstExisting(scriptCandidates);
  if (!bridge) {
    throw new BridgeError(
      'Could not find vscode_bridge.py.',
      'Set "coverityTool.bridgePath" to the file inside your Coverity-Tool checkout, ' +
      'or open the Coverity-Tool repository as the workspace folder.');
  }
  const bridgeDir = path.dirname(bridge);

  const configuredPython = (config.get<string>('pythonPath') || '').trim();
  const venvNames = process.platform === 'win32'
    ? [path.join('.venv', 'Scripts', 'python.exe')]
    : [path.join('.venv', 'bin', 'python3'), path.join('.venv', 'bin', 'python')];

  const venvCandidates: string[] = [];
  for (const folder of workspaceFolders) {
    for (const rel of venvNames) {
      venvCandidates.push(path.join(folder.uri.fsPath, rel));
    }
  }
  for (const rel of venvNames) {
    venvCandidates.push(path.join(bridgeDir, rel));
    venvCandidates.push(path.join(path.dirname(bridgeDir), rel));
  }

  // An explicitly configured interpreter always wins (it may be a bare name
  // that the OS resolves through PATH). Otherwise prefer a virtualenv next to
  // the tool, and only then fall back to the platform's default name.
  const pathPython = firstExisting(venvCandidates);
  const defaultPython = process.platform === 'win32' ? 'python' : 'python3';
  const python = configuredPython || pathPython || defaultPython;

  return { python, bridge, cwd: bridgeDir };
}

// --------------------------------------------------------------------------- //
// Running a subcommand
// --------------------------------------------------------------------------- //
export interface RunOptions {
  token?: vscode.CancellationToken;
  timeoutMs?: number;
  onProgress?: (done: number, total: number, label: string) => void;
  cwd?: string;
}

interface BridgeEnvelope {
  ok: boolean;
  schema: number;
  error?: { type?: string; message?: string; hint?: string };
  [key: string]: unknown;
}

const PROGRESS_PATTERN = /^\[(\d+)\/(\d+)\]\s+(.*)$/;

/**
 * Run `vscode_bridge.py <args...>` and return its parsed JSON payload.
 *
 * Progress lines the bridge writes to stderr are forwarded to `onProgress`, so
 * a long triage can drive a real progress bar instead of a spinner.
 */
export async function runBridge<T>(args: string[], options: RunOptions = {}): Promise<T> {
  const context = getExtensionContext();
  const { python, bridge, cwd } = locateBridge(context);
  const timeoutMs = options.timeoutMs ?? 900_000;

  return new Promise<T>((resolve, reject) => {
    let child: childProcess.ChildProcessWithoutNullStreams;
    try {
      child = childProcess.spawn(python, [bridge, ...args], {
        cwd: options.cwd || cwd,
        windowsHide: true,
      });
    } catch (err) {
      reject(new BridgeError(
        `Could not start "${python}": ${(err as Error).message}`,
        'Set "coverityTool.pythonPath" to a Python 3.10+ interpreter that has the ' +
        'tool\'s requirements installed.'));
      return;
    }

    const stdoutChunks: Buffer[] = [];
    const stderrTail: string[] = [];
    let settled = false;
    let timer: NodeJS.Timeout | undefined;
    let lineBuffer = '';
    let disposable: vscode.Disposable | undefined;

    const finish = (fn: () => void) => {
      if (settled) {
        return;
      }
      settled = true;
      if (timer) {
        clearTimeout(timer);
      }
      disposable?.dispose();
      fn();
    };

    disposable = options.token?.onCancellationRequested(() => {
      try {
        child.kill();
      } catch {
        /* already gone */
      }
      finish(() => reject(new vscode.CancellationError()));
    });

    if (timeoutMs > 0) {
      timer = setTimeout(() => {
        try {
          child.kill();
        } catch {
          /* already gone */
        }
        finish(() => reject(new BridgeError(
          `Analysis exceeded ${Math.round(timeoutMs / 1000)}s and was stopped.`,
          'Raise "coverityTool.timeoutSeconds", or narrow the run with a lower ' +
          '"coverityTool.maxDefects".')));
      }, timeoutMs);
    }

    child.stdout.on('data', (chunk: Buffer) => stdoutChunks.push(chunk));
    child.stderr.on('data', (chunk: Buffer) => {
      lineBuffer += chunk.toString('utf8');
      const lines = lineBuffer.split(/\r?\n/);
      lineBuffer = lines.pop() ?? '';
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) {
          continue;
        }
        stderrTail.push(trimmed);
        if (stderrTail.length > 40) {
          stderrTail.shift();
        }
        const match = PROGRESS_PATTERN.exec(trimmed);
        if (match && options.onProgress) {
          options.onProgress(Number(match[1]), Number(match[2]), match[3]);
        }
      }
    });

    child.on('error', (err: Error) => {
      finish(() => reject(new BridgeError(
        `Failed to run the Coverity bridge: ${err.message}`,
        `Interpreter: ${python}`)));
    });

    child.on('close', (code: number | null) => {
      finish(() => {
        const stdout = Buffer.concat(stdoutChunks).toString('utf8').trim();
        let envelope: BridgeEnvelope | undefined;
        if (stdout) {
          // --jsonl prints several objects; take the last one (the summary).
          const lines = stdout.split(/\r?\n/).filter(l => l.trim().startsWith('{'));
          for (let i = lines.length - 1; i >= 0 && !envelope; i--) {
            try {
              envelope = JSON.parse(lines[i]) as BridgeEnvelope;
            } catch {
              /* keep looking */
            }
          }
        }

        if (envelope && envelope.ok === false) {
          const err = envelope.error ?? {};
          reject(new BridgeError(err.message || 'The Coverity tool reported an error.',
            err.hint || undefined));
          return;
        }
        if (!envelope) {
          const tail = stderrTail.slice(-8).join('\n');
          reject(new BridgeError(
            `The Coverity bridge returned no JSON (exit code ${code ?? 'null'}).`,
            tail || `Command: ${python} ${bridge} ${args.join(' ')}`));
          return;
        }
        if (code !== 0 && envelope.ok !== true) {
          reject(new BridgeError(`The Coverity bridge exited with code ${code}.`,
            stderrTail.slice(-5).join('\n')));
          return;
        }
        resolve(envelope as unknown as T);
      });
    });
  });
}

// --------------------------------------------------------------------------- //
// The extension context is stored once at activation so the tool classes (which
// VS Code constructs without arguments) can reach it too.
// --------------------------------------------------------------------------- //
let extensionContext: vscode.ExtensionContext | undefined;

export function setExtensionContext(context: vscode.ExtensionContext): void {
  extensionContext = context;
}

export function getExtensionContext(): vscode.ExtensionContext {
  if (!extensionContext) {
    throw new BridgeError('The Coverity Tool extension has not finished activating.');
  }
  return extensionContext;
}

// --------------------------------------------------------------------------- //
// Configuration helpers
// --------------------------------------------------------------------------- //
export interface RunSettings {
  report: string;
  srcRoot: string;
  language: string;
  maxDefects: number;
  timeoutMs: number;
}

export function readSettings(): RunSettings {
  const config = vscode.workspace.getConfiguration('coverityTool');
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
  const raw = (value: string) =>
    (value || '').replace(/\$\{workspaceFolder\}/g, workspaceFolder).trim();

  return {
    report: raw(config.get<string>('reportPath') || ''),
    srcRoot: raw(config.get<string>('sourceRoot') || ''),
    language: (config.get<string>('language') || 'c').toLowerCase(),
    maxDefects: Math.max(1, Number(config.get<number>('maxDefects') ?? 100)),
    timeoutMs: Math.max(10, Number(config.get<number>('timeoutSeconds') ?? 900)) * 1000,
  };
}

/** Ask for the report path if the setting is empty; returns '' if cancelled. */
export async function ensureReportPath(settings: RunSettings): Promise<string> {
  if (settings.report) {
    return settings.report;
  }
  const picked = await vscode.window.showOpenDialog({
    title: 'Select the Coverity report (index.html or .xlsx)',
    canSelectFiles: true,
    canSelectFolders: true,
    canSelectMany: false,
    openLabel: 'Use this report',
    filters: { 'Coverity report': ['html', 'htm', 'xlsx', 'xlsm', 'json'] },
  });
  if (!picked || picked.length === 0) {
    return '';
  }
  const chosen = picked[0].fsPath;
  const stat = await vscode.workspace.fs.stat(picked[0]);
  const report = (stat.type & vscode.FileType.Directory) === vscode.FileType.Directory
    ? path.join(chosen, 'index.html')
    : chosen;
  await vscode.workspace.getConfiguration('coverityTool').update(
    'reportPath', report, vscode.ConfigurationTarget.Workspace);
  return report;
}
