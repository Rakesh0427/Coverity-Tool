/**
 * Coverity Tool — VS Code extension entry point.
 *
 * Two ways to use it, both backed by the same Python engine:
 *   • a human: "Coverity: Analyse Report" → Findings view + Problems panel,
 *   • an agent: the `coverityTool_*` language-model tools (or the MCP server in
 *     coverity_mcp_server.py for clients that speak MCP).
 */

import * as path from 'path';
import * as vscode from 'vscode';
import {
  BridgeError,
  CapabilitiesPayload,
  DefectSummary,
  isCancellation,
  readSettings,
  runBridge,
  setExtensionContext,
} from './bridge';
import {
  FileNode,
  FindingNode,
  FindingsProvider,
  FindingsStore,
  copyRationale,
  openFinding,
  showFindingAtCursor,
  triageWithUi,
} from './findings';
import { dispositionsCsv } from './dispositions';
import { registerTools } from './tools';

let store: FindingsStore;
let output: vscode.OutputChannel;
let statusBar: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext): void {
  store = new FindingsStore();
  output = vscode.window.createOutputChannel('Coverity Tool');
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  statusBar.command = 'coverityTool.runAnalysis';
  statusBar.text = '$(shield) Coverity';
  statusBar.tooltip = 'Coverity Tool — run a triage';
  statusBar.show();

  setExtensionContext(context);
  registerTools(context, store);

  const provider = new FindingsProvider(store);
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('coverityTool.findings', provider),
    store,
    output,
    statusBar,
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('coverityTool.runAnalysis', async () => {
      const payload = await triageWithUi(store);
      if (payload) {
        reportToOutput(payload.report, payload.summary, payload.capabilities);
        if (payload.defects.length) {
          await vscode.commands.executeCommand('coverityTool.findings.focus');
        }
      }
      updateStatusBar();
    }),

    vscode.commands.registerCommand('coverityTool.refresh', () => {
      const count = store.loadCachedAnnotations();
      updateStatusBar();
      vscode.window.showInformationMessage(
        count
          ? `Coverity: reloaded ${count} cached finding(s) from .coverity/`
          : 'Coverity: no cached triage found in .coverity/ — run "Coverity: Analyse Report".');
    }),

    vscode.commands.registerCommand('coverityTool.showCapabilities', async () => {
      try {
        const payload = await runBridge<{ capabilities: CapabilitiesPayload }>(['capabilities']);
        output.clear();
        output.appendLine(payload.capabilities.banner ||
          `analysis depth: ${payload.capabilities.depth}`);
        output.appendLine('');
        for (const backend of payload.capabilities.backends ?? []) {
          output.appendLine(
            `${backend.available ? '[ok]     ' : '[missing]'} ${backend.label} — ${backend.detail}`);
        }
        if (payload.capabilities.missing?.length) {
          output.appendLine('');
          output.appendLine('Install the full dependency set for maximum accuracy:');
          output.appendLine('  pip install -r requirements.txt');
        }
        output.show(true);
      } catch (err) {
        showError(err);
      }
    }),

    vscode.commands.registerCommand('coverityTool.exportTriage', async () => {
      if (store.all.length === 0) {
        vscode.window.showWarningMessage(
          'Coverity: nothing to export — run "Coverity: Analyse Report" first.');
        return;
      }
      const target = await vscode.window.showSaveDialog({
        title: 'Export Coverity triage',
        filters: { 'Triage JSON': ['json'], 'Comma separated': ['csv'] },
        saveLabel: 'Export',
      });
      if (!target) {
        return;
      }
      const text = target.fsPath.toLowerCase().endsWith('.csv')
        ? dispositionsCsv(store.all)
        : toAnnotationJson(store);
      await vscode.workspace.fs.writeFile(target, Buffer.from(text, 'utf8'));
      const isCsv = target.fsPath.toLowerCase().endsWith('.csv');
      const openIt = await vscode.window.showInformationMessage(
        isCsv
          ? `Dispositions exported to ${path.basename(target.fsPath)} — load it on the `
            + 'Coverity Findings Analyzer Push page to push these dispositions.'
          : `Coverity triage exported to ${path.basename(target.fsPath)}`, 'Open');
      if (openIt) {
        await vscode.window.showTextDocument(target);
      }
    }),

    vscode.commands.registerCommand('coverityTool.openFinding', (node: FindingNode) =>
      openFinding(node)),

    vscode.commands.registerCommand('coverityTool.copyRationale', async (node: FindingNode) => {
      if (node instanceof FindingNode) {
        await copyRationale(node);
      }
    }),

    vscode.commands.registerCommand('coverityTool.analyzeAtCursor', () =>
      showFindingAtCursor(store)),
  );

  // Reload the last cached triage so a reopened window shows findings without
  // paying for the analysis again.
  try {
    store.loadCachedAnnotations();
  } catch (err) {
    output.appendLine(`Could not reload cached triage: ${(err as Error).message}`);
  }
  updateStatusBar();
}

export function deactivate(): void {
  store?.dispose();
}

// --------------------------------------------------------------------------- //
// Helpers
// --------------------------------------------------------------------------- //
function updateStatusBar(): void {
  const findings = store?.all ?? [];
  if (findings.length === 0) {
    statusBar.text = '$(shield) Coverity';
    statusBar.tooltip = 'Coverity Tool — no triage loaded. Click to analyse a report.';
    return;
  }
  const bugs = findings.filter(f => f.disposition === 'Bug').length;
  const needsReview = findings.filter(f => f.disposition === 'Needs review').length;
  statusBar.text = `$(shield) ${findings.length} findings` +
    (bugs ? ` · $(bug) ${bugs}` : '') +
    (needsReview ? ` · $(question) ${needsReview}` : '');
  statusBar.tooltip = `Coverity Tool — ${findings.length} findings loaded` +
    (store.analysisDepth !== 'full' ? ` (analysis depth: ${store.analysisDepth})` : '');
}

function reportToOutput(report: string, summary: DefectSummary, caps: CapabilitiesPayload | undefined): void {
  output.appendLine('');
  output.appendLine(`Report: ${report}`);
  output.appendLine(`Defects: ${summary.total} — Bug ${summary.bug}, ` +
    `False positive ${summary.false_positive}, Intentional ${summary.intentional}, ` +
    `Needs review ${summary.needs_review}`);
  output.appendLine(`Mean confidence: ${summary.mean_confidence}`);
  if (caps && caps.depth !== 'full') {
    output.appendLine(`Analysis depth: ${caps.depth} — missing ${caps.missing.join(', ')}`);
  }
}

function showError(err: unknown): void {
  if (isCancellation(err)) {
    return;
  }
  if (err instanceof BridgeError) {
    vscode.window.showErrorMessage(err.toText(), 'Show Log').then(choice => {
      if (choice === 'Show Log') {
        output.show(true);
      }
    });
    output.appendLine(`[error] ${err.toText()}`);
    return;
  }
  const message = (err as Error)?.message ?? String(err);
  output.appendLine(`[error] ${message}`);
  vscode.window.showErrorMessage(`Coverity Tool: ${message}`);
}

function toAnnotationJson(current: FindingsStore): string {
  const settings = readSettings();
  return JSON.stringify({
    schema: 1,
    tool: 'coverity-tool',
    generated_at: new Date().toISOString(),
    report: current.report,
    src_root: current.sourceRoot || settings.srcRoot,
    language: settings.language,
    capabilities: current.lastCapabilities ?? {},
    summary: current.lastSummary ?? {},
    defects: current.all,
  }, null, 2);
}

// Re-exported so the tree view's node types are part of the public surface of
// the extension (useful if another extension wants to reuse them).
export { FindingNode, FileNode };
