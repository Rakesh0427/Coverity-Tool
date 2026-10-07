/**
 * Findings store, Problems-panel integration and the Findings tree view.
 *
 * The store is the single place the triage results live in the editor. Both the
 * extension commands and the language-model tools write into it, so a tool call
 * from Copilot and a click in the tree view see exactly the same data.
 */

import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';
import {
  AnalyzePayload,
  AnnotationFile,
  BridgeError,
  DefectRecord,
  isCancellation,
  readSettings,
  runBridge,
} from './bridge';

// --------------------------------------------------------------------------- //
// Result cache on disk
// --------------------------------------------------------------------------- //
export function annotationDirectory(): string {
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  return folder ? path.join(folder, '.coverity') : '';
}

function safeBaseName(report: string): string {
  const base = path.basename(report, path.extname(report)) || 'report';
  return base.replace(/[^A-Za-z0-9._-]/g, '_');
}

export function annotationPathFor(report: string): string {
  const dir = annotationDirectory();
  return dir ? path.join(dir, `${safeBaseName(report)}.triage.json`) : '';
}

// --------------------------------------------------------------------------- //
// Store
// --------------------------------------------------------------------------- //
export class FindingsStore {
  private readonly changeEmitter = new vscode.EventEmitter<void>();
  readonly onDidChange = this.changeEmitter.event;

  private findings: DefectRecord[] = [];
  private reportPath = '';
  private srcRoot = '';
  private depth = 'unknown';
  private summary: AnalyzePayload['summary'] | undefined;
  private capabilities: AnalyzePayload['capabilities'] | undefined;

  private readonly diagnostics = vscode.languages.createDiagnosticCollection('coverity-tool');

  dispose(): void {
    this.diagnostics.dispose();
    this.changeEmitter.dispose();
  }

  get all(): DefectRecord[] {
    return this.findings;
  }

  get report(): string {
    return this.reportPath;
  }

  get analysisDepth(): string {
    return this.depth;
  }

  get sourceRoot(): string {
    return this.srcRoot;
  }

  get lastSummary(): AnalyzePayload['summary'] | undefined {
    return this.summary;
  }

  get lastCapabilities(): AnalyzePayload['capabilities'] | undefined {
    return this.capabilities;
  }

  get(cid: number): DefectRecord | undefined {
    return this.findings.find(f => f.cid === cid);
  }

  byFile(): Map<string, DefectRecord[]> {
    const grouped = new Map<string, DefectRecord[]>();
    for (const finding of this.findings) {
      const key = finding.resolved_file || finding.file;
      if (!key) {
        continue;
      }
      const list = grouped.get(key) ?? [];
      list.push(finding);
      grouped.set(key, list);
    }
    return grouped;
  }

  /** Replace the current results with a finished analysis payload. */
  setFromPayload(payload: AnalyzePayload): void {
    this.reportPath = payload.report;
    this.srcRoot = payload.src_root;
    this.depth = payload.capabilities?.depth ?? 'unknown';
    this.summary = payload.summary;
    this.capabilities = payload.capabilities;
    this.findings = (payload.defects ?? []).map(normaliseRecord);
    this.publishDiagnostics();
    this.changeEmitter.fire();
  }

  /** Reload a `.triage.json` written by an earlier run (CLI, MCP or this extension). */
  loadAnnotation(file: string): void {
    const text = fs.readFileSync(file, 'utf8');
    const parsed = JSON.parse(text) as AnnotationFile;
    this.reportPath = parsed.report || '';
    this.srcRoot = parsed.src_root || '';
    this.depth = parsed.capabilities?.depth ?? 'unknown';
    this.summary = parsed.summary;
    this.capabilities = parsed.capabilities;
    this.findings = (parsed.defects ?? []).map(normaliseRecord);
    this.publishDiagnostics();
    this.changeEmitter.fire();
  }

  /** Load every cached triage in `<workspace>/.coverity` (used on activation). */
  loadCachedAnnotations(): number {
    const dir = annotationDirectory();
    if (!dir || !fs.existsSync(dir)) {
      return 0;
    }
    const files = fs.readdirSync(dir).filter(f => f.endsWith('.triage.json'));
    if (files.length === 0) {
      return 0;
    }
    let newest: { file: string; mtime: number } | undefined;
    for (const name of files) {
      const full = path.join(dir, name);
      const stat = fs.statSync(full);
      if (!newest || stat.mtimeMs > newest.mtime) {
        newest = { file: full, mtime: stat.mtimeMs };
      }
    }
    if (!newest) {
      return 0;
    }
    this.loadAnnotation(newest.file);
    return this.findings.length;
  }

  // ------------------------------------------------------------------ //
  // Problems panel
  // ------------------------------------------------------------------ //
  private publishDiagnostics(): void {
    this.diagnostics.clear();
    const config = vscode.workspace.getConfiguration('coverityTool');
    if (!config.get<boolean>('publishDiagnostics', true)) {
      return;
    }
    const allowed = new Set(config.get<string[]>('diagnosticDispositions', ['Bug', 'Needs review']));

    const byUri = new Map<string, vscode.Diagnostic[]>();
    for (const finding of this.findings) {
      if (!allowed.has(finding.disposition)) {
        continue;
      }
      const filePath = finding.resolved_file || finding.file;
      if (!filePath || !path.isAbsolute(filePath) || !fs.existsSync(filePath)) {
        // Diagnose only files the workspace can actually open; report-only
        // paths (a CI machine's layout) would show up as broken entries.
        continue;
      }
      const zeroBased = Math.max(0, (finding.line || 1) - 1);
      const range = new vscode.Range(zeroBased, 0, zeroBased, Number.MAX_SAFE_INTEGER);
      const message = diagnosticMessage(finding);
      const diagnostic = new vscode.Diagnostic(range, message, severityFor(finding.disposition));
      diagnostic.source = 'Coverity';
      diagnostic.code = finding.checker;
      const cwe = /CWE-\d+/i.exec(finding.comment || '');
      if (cwe) {
        const id = cwe[0].toUpperCase().replace('CWE-', '');
        diagnostic.code = {
          value: `${finding.checker} · ${cwe[0].toUpperCase()}`,
          target: vscode.Uri.parse(`https://cwe.mitre.org/data/definitions/${id}.html`),
        };
      }
      const list = byUri.get(filePath) ?? [];
      list.push(diagnostic);
      byUri.set(filePath, list);
    }
    for (const [filePath, list] of byUri) {
      this.diagnostics.set(vscode.Uri.file(filePath), list);
    }
  }
}

function diagnosticMessage(finding: DefectRecord): string {
  const confidence = Math.round((finding.confidence || 0) * 100);
  const head = `Coverity ${finding.checker}: ${finding.disposition} (confidence ${confidence}%).`;
  const rationale = (finding.comment || '').replace(/\s+/g, ' ').trim();
  const fix = finding.proposed_fix && finding.proposed_fix !== 'No fix required.'
    ? ` Suggested fix: ${finding.proposed_fix.replace(/\s+/g, ' ').trim()}`
    : '';
  return `${head} ${rationale}${fix}`.slice(0, 2000);
}

function severityFor(disposition: string): vscode.DiagnosticSeverity {
  switch (disposition) {
    case 'Bug':
      return vscode.DiagnosticSeverity.Error;
    case 'Needs review':
      return vscode.DiagnosticSeverity.Warning;
    case 'False positive':
      return vscode.DiagnosticSeverity.Information;
    default:
      return vscode.DiagnosticSeverity.Hint;
  }
}

function normaliseRecord(record: DefectRecord): DefectRecord {
  return {
    ...record,
    cid: Number(record.cid) || 0,
    line: Number(record.line) || 0,
    confidence: Number(record.confidence) || 0,
    comment: record.comment || '',
    proposed_fix: record.proposed_fix || '',
  };
}

// --------------------------------------------------------------------------- //
// Tree view
// --------------------------------------------------------------------------- //
export class FindingNode extends vscode.TreeItem {
  constructor(public readonly finding: DefectRecord) {
    super(`CID ${finding.cid} · ${finding.checker}`,
      vscode.TreeItemCollapsibleState.None);
    const confidence = Math.round((finding.confidence || 0) * 100);
    this.description = `${finding.disposition} · ${confidence}%`;
    this.contextValue = 'coverityFinding';
    this.iconPath = new vscode.ThemeIcon(iconFor(finding.disposition));
    this.tooltip = new vscode.MarkdownString(
      `**CID ${finding.cid} — ${finding.checker}**\n\n` +
      `*${finding.disposition}* · confidence ${confidence}%\n\n` +
      `${finding.comment || ''}\n\n` +
      (finding.proposed_fix ? `**Suggested fix**\n\n\`\`\`c\n${finding.proposed_fix}\n\`\`\`` : ''));
    const filePath = finding.resolved_file || finding.file;
    if (filePath) {
      const zeroBased = Math.max(0, (finding.line || 1) - 1);
      this.command = {
        command: 'coverityTool.openFinding',
        title: 'Open finding',
        arguments: [this],
      };
      this.resourceUri = vscode.Uri.file(filePath).with({ fragment: String(zeroBased + 1) });
    }
  }
}

export class FileNode extends vscode.TreeItem {
  constructor(public readonly filePath: string, public readonly findings: DefectRecord[]) {
    super(path.basename(filePath), vscode.TreeItemCollapsibleState.Expanded);
    const bugs = findings.filter(f => f.disposition === 'Bug').length;
    this.description = `${findings.length} finding${findings.length === 1 ? '' : 's'}` +
      (bugs ? ` · ${bugs} bug${bugs === 1 ? '' : 's'}` : '');
    this.tooltip = filePath;
    this.iconPath = vscode.ThemeIcon.File;
    this.resourceUri = vscode.Uri.file(filePath);
  }
}

function iconFor(disposition: string): string {
  switch (disposition) {
    case 'Bug':
      return 'bug';
    case 'Needs review':
      return 'question';
    case 'False positive':
      return 'pass';
    default:
      return 'circle-outline';
  }
}

export class FindingsProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly changeEmitter = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changeEmitter.event;

  constructor(private readonly store: FindingsStore) {
    store.onDidChange(() => this.changeEmitter.fire());
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: vscode.TreeItem): vscode.TreeItem[] {
    if (!element) {
      if (this.store.all.length === 0) {
        return [];
      }
      const grouped = this.store.byFile();
      return [...grouped.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([file, findings]) =>
          new FileNode(file, [...findings].sort((x, y) => (x.line || 0) - (y.line || 0))));
    }
    if (element instanceof FileNode) {
      return element.findings.map(f => new FindingNode(f));
    }
    return [];
  }
}

// --------------------------------------------------------------------------- //
// Commands
// --------------------------------------------------------------------------- //
export async function openFinding(node: FindingNode | DefectRecord): Promise<void> {
  const finding = node instanceof FindingNode ? node.finding : node;
  const filePath = finding.resolved_file || finding.file;
  if (!filePath || !path.isAbsolute(filePath) || !fs.existsSync(filePath)) {
    vscode.window.showWarningMessage(
      `Coverity CID ${finding.cid}: the source file "${finding.file}" was not found locally. ` +
      'Set "coverityTool.sourceRoot" to the analysed checkout and re-run the analysis.');
    return;
  }
  const document = await vscode.workspace.openTextDocument(vscode.Uri.file(filePath));
  const editor = await vscode.window.showTextDocument(document);
  const line = Math.max(0, (finding.line || 1) - 1);
  const position = new vscode.Position(line, 0);
  editor.selection = new vscode.Selection(position, position);
  editor.revealRange(new vscode.Range(position, position), vscode.TextEditorRevealType.InCenter);
}

export async function copyRationale(node: FindingNode | DefectRecord): Promise<void> {
  const finding = node instanceof FindingNode ? node.finding : node;
  const payload = [
    `CID ${finding.cid} — ${finding.checker} (${finding.disposition}, ` +
    `${Math.round((finding.confidence || 0) * 100)}% confidence)`,
    `${finding.resolved_file || finding.file}:${finding.line || '?'}` +
    (finding.function ? ` in ${finding.function}()` : ''),
    '',
    finding.comment || '',
    '',
    finding.proposed_fix ? `Suggested fix: ${finding.proposed_fix}` : '',
  ].join('\n');
  await vscode.env.clipboard.writeText(payload);
  vscode.window.setStatusBarMessage(`Coverity CID ${finding.cid} rationale copied`, 3000);
}

/** Explain the finding(s) on the line under the cursor (editor context menu). */
export async function showFindingAtCursor(store: FindingsStore): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    return;
  }
  const filePath = editor.document.uri.fsPath;
  const line = editor.selection.active.line + 1;
  const inFile = store.all
    .filter(f => (f.resolved_file || f.file) === filePath)
    .sort((a, b) => Math.abs((a.line || 0) - line) - Math.abs((b.line || 0) - line));

  if (inFile.length === 0) {
    const action = await vscode.window.showInformationMessage(
      'No Coverity analysis is loaded for this file. Run "Coverity: Analyse Report" first.',
      'Analyse Report');
    if (action) {
      await vscode.commands.executeCommand('coverityTool.runAnalysis');
    }
    return;
  }

  const nearest = inFile[0];
  const distance = Math.abs((nearest.line || 0) - line);
  const pick = await vscode.window.showQuickPick([
    {
      label: `$(bug) CID ${nearest.cid} · ${nearest.checker}`,
      description: `${nearest.disposition} · ${Math.round(nearest.confidence * 100)}%` +
        (distance ? ` · ${distance} line(s) away` : ' · this line'),
      detail: (nearest.comment || '').replace(/\s+/g, ' ').slice(0, 200),
      finding: nearest as DefectRecord,
    },
    ...inFile.slice(0, 20).map(f => ({
      label: `$(circle-outline) CID ${f.cid} · ${f.checker}`,
      description: `${f.disposition} · line ${f.line || '?'}`,
      detail: (f.comment || '').replace(/\s+/g, ' ').slice(0, 200),
      finding: f,
    })),
  ], { title: `Coverity findings in ${path.basename(filePath)}` });

  if (!pick) {
    return;
  }
  await showRationaleDocument(pick.finding);
}

async function showRationaleDocument(finding: DefectRecord): Promise<void> {
  const body = [
    `# CID ${finding.cid} — ${finding.checker}`,
    '',
    `**Disposition:** ${finding.disposition} · confidence ${Math.round((finding.confidence || 0) * 100)}%`,
    '',
    `**Location:** \`${finding.resolved_file || finding.file}:${finding.line || '?'}\`` +
    (finding.function ? ` in \`${finding.function}()\`` : ''),
    '',
    '## Rationale',
    '',
    finding.comment || '_(no rationale recorded)_',
    '',
  ];
  if (finding.proposed_fix) {
    body.push('## Suggested fix', '', '```c', finding.proposed_fix, '```', '');
  }
  if (finding.source_context?.code) {
    body.push('## Source', '', '```c', finding.source_context.code, '```', '');
  }
  const document = await vscode.workspace.openTextDocument({
    language: 'markdown',
    content: body.join('\n'),
  });
  await vscode.window.showTextDocument(document, { preview: true, viewColumn: vscode.ViewColumn.Beside });
}

// --------------------------------------------------------------------------- //
// The one place that actually runs a triage, shared by the command and the
// language-model tool, so both report identical results.
// --------------------------------------------------------------------------- //
export interface TriageRunOptions {
  report: string;
  srcRoot?: string;
  language?: string;
  limit?: number;
  checker?: string;
  severity?: string;
  token?: vscode.CancellationToken;
  onProgress?: (done: number, total: number, label: string) => void;
}

export async function runTriage(
  store: FindingsStore,
  options: TriageRunOptions,
): Promise<AnalyzePayload> {
  const settings = readSettings();
  const args = [
    'analyze',
    '--report', options.report,
    '--language', options.language || settings.language,
    '--limit', String(options.limit ?? settings.maxDefects),
  ];
  const srcRoot = options.srcRoot ?? settings.srcRoot;
  if (srcRoot) {
    args.push('--src', srcRoot);
  }
  if (options.checker) {
    args.push('--checker', options.checker);
  }
  if (options.severity) {
    args.push('--severity', options.severity);
  }
  const annotation = annotationPathFor(options.report);
  if (annotation) {
    args.push('--out', annotation);
  }

  const payload = await runBridge<AnalyzePayload>(args, {
    token: options.token,
    timeoutMs: settings.timeoutMs,
    onProgress: options.onProgress,
  });
  store.setFromPayload(payload);
  return payload;
}

export async function triageWithUi(store: FindingsStore): Promise<AnalyzePayload | undefined> {
  const settings = readSettings();
  let report = settings.report;
  if (!report) {
    const picked = await vscode.window.showOpenDialog({
      title: 'Select the Coverity report (index.html, its folder, or .xlsx)',
      canSelectFiles: true,
      canSelectFolders: true,
      canSelectMany: false,
      filters: { 'Coverity report': ['html', 'htm', 'xlsx', 'xlsm'] },
    });
    if (!picked || picked.length === 0) {
      return undefined;
    }
    const isDir = (await vscode.workspace.fs.stat(picked[0])).type & vscode.FileType.Directory;
    report = isDir ? path.join(picked[0].fsPath, 'index.html') : picked[0].fsPath;
  }

  try {
    return await vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: `Coverity: analysing ${path.basename(report)}`,
      cancellable: true,
    }, async (progress, token) => {
      const payload = await runTriage(store, {
        report,
        token,
        onProgress: (done, total, label) => {
          progress.report({
            increment: total ? 100 / total : 0,
            message: `${done}/${total} ${label}`,
          });
        },
      });
      const summary = payload.summary;
      vscode.window.showInformationMessage(
        `Coverity: ${summary.total} defects — Bug ${summary.bug}, ` +
        `False positive ${summary.false_positive}, Intentional ${summary.intentional}, ` +
        `Needs review ${summary.needs_review}` +
        (payload.capabilities?.depth && payload.capabilities.depth !== 'full'
          ? ` (analysis depth: ${payload.capabilities.depth})`
          : ''));
      return payload;
    });
  } catch (err) {
    if (isCancellation(err)) {
      return undefined;
    }
    if (err instanceof BridgeError) {
      vscode.window.showErrorMessage(err.toText());
      return undefined;
    }
    throw err;
  }
}
