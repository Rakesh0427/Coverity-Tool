/**
 * Language-model tools (GitHub Copilot agent mode / chat `#` references).
 *
 * Each class here is registered with `vscode.lm.registerTool` under the same
 * name that `package.json` contributes, and each one ultimately calls the same
 * Python bridge the commands do. Nothing is re-implemented in TypeScript: an
 * agent asking for a verdict gets the exact answer the GUI would print.
 */

import * as path from 'path';
import * as vscode from 'vscode';
import {
  BridgeError,
  CapabilitiesPayload,
  DefectRecord,
  isCancellation,
  ListPayload,
  readSettings,
  runBridge,
} from './bridge';
import { FindingsStore, runTriage } from './findings';

// --------------------------------------------------------------------------- //
// Shared helpers
// --------------------------------------------------------------------------- //
function workspaceRoot(): string {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd();
}

function resolveUserPath(value: string): string {
  if (!value) {
    return '';
  }
  return path.isAbsolute(value) ? value : path.join(workspaceRoot(), value);
}

function reportFrom(input: { report?: string }): string {
  const settings = readSettings();
  const chosen = resolveUserPath((input.report || '').trim()) || settings.report;
  if (!chosen) {
    throw new BridgeError(
      'No Coverity report is configured.',
      'Set "coverityTool.reportPath" in Settings (or pass `report` to this tool). ' +
      'It should point at Coverity\'s index.html, the folder containing it, or an .xlsx export.');
  }
  return chosen;
}

function srcRootFrom(input: { src_root?: string }): string {
  const settings = readSettings();
  return resolveUserPath((input.src_root || '').trim()) || settings.srcRoot;
}

function textResult(...parts: string[]): vscode.LanguageModelToolResult {
  return new vscode.LanguageModelToolResult(
    parts.map(p => new vscode.LanguageModelTextPart(p)));
}

function errorResult(err: unknown): vscode.LanguageModelToolResult {
  if (err instanceof BridgeError) {
    return textResult(err.toText());
  }
  return textResult(`Coverity analysis failed: ${(err as Error).message}`);
}

function percent(value: number): number {
  return Math.round((value || 0) * 100);
}

function formatDefect(record: DefectRecord, withEvents = false): string {
  const lines = [
    `### CID ${record.cid} — ${record.checker} (${record.category || 'uncategorised'})`,
    `- Disposition: **${record.disposition}** (confidence ${percent(record.confidence)}%)`,
    `- Location: ${record.resolved_file || record.file || 'unknown'}:${record.line || '?'}` +
    (record.function ? ` in \`${record.function}()\`` : ''),
  ];
  if (record.severity) {
    lines.push(`- Severity: ${record.severity}`);
  }
  if (record.type) {
    lines.push(`- Coverity type: ${record.type}`);
  }
  if (record.comment) {
    lines.push(`- Rationale: ${record.comment}`);
  }
  if (record.proposed_fix) {
    lines.push(`- Suggested fix: \`${record.proposed_fix}\``);
  }
  if (record.source_context?.code) {
    lines.push('- Source (numbered):');
    lines.push('```c');
    lines.push(record.source_context.code);
    lines.push('```');
  }
  if (withEvents && record.events?.length) {
    lines.push('- Event trace:');
    for (const event of record.events) {
      lines.push(`  ${event.step ?? '?'}. [${event.type ?? '?'}] ${event.description ?? ''} ` +
        `(${event.file ?? '?'}:${event.line ?? '?'})`);
    }
  }
  return lines.join('\n');
}

function depthWarning(caps: CapabilitiesPayload | undefined): string {
  if (!caps || caps.depth === 'full') {
    return '';
  }
  return `\n_Note: analysis depth is **${caps.depth}** ` +
    `(missing: ${caps.missing.join(', ') || 'unknown'}). Verdicts are still useful, ` +
    `but the 'Needs review' rate is higher than on a machine with the full ` +
    `requirements installed._\n`;
}

function requireCid(input: { cid?: number }): number {
  const cid = Number(input.cid);
  if (!Number.isFinite(cid) || cid <= 0) {
    throw new BridgeError(
      'A numeric Coverity defect id (CID) is required.',
      'Use the list-defects tool (or the Findings view) to find the CID.');
  }
  return cid;
}

// --------------------------------------------------------------------------- //
// coverityTool_capabilities
// --------------------------------------------------------------------------- //
interface CapabilitiesInput {
  refresh?: boolean;
}

export class CapabilitiesTool implements vscode.LanguageModelTool<CapabilitiesInput> {
  constructor(private readonly store: FindingsStore) { }

  prepareInvocation(): vscode.PreparedToolInvocation {
    return { invocationMessage: 'Checking Coverity analysis backends…' };
  }

  async invoke(options: vscode.LanguageModelToolInvocationOptions<CapabilitiesInput>): Promise<vscode.LanguageModelToolResult> {
    try {
      if (!options.input?.refresh && this.store.lastCapabilities) {
        return textResult(this.render(this.store.lastCapabilities, true));
      }
      const payload = await runBridge<{ capabilities: CapabilitiesPayload }>(['capabilities']);
      return textResult(this.render(payload.capabilities, false));
    } catch (err) {
      return errorResult(err);
    }
  }

  private render(caps: CapabilitiesPayload, cached: boolean): string {
    const lines = [
      `Analysis depth: **${(caps.depth || 'unknown').toUpperCase()}**` +
      (cached ? ' (from the last run in this window)' : ''),
      '',
    ];
    for (const backend of caps.backends ?? []) {
      lines.push(`- ${backend.label}: ${backend.available ? 'available' : 'UNAVAILABLE'} ` +
        `— ${backend.detail}`);
    }
    if (caps.missing?.length) {
      lines.push('');
      lines.push(`Missing critical backends: ${caps.missing.join(', ')}. ` +
        'Install them with `pip install -r requirements.txt` for full-strength verdicts.');
    }
    return lines.join('\n');
  }
}

// --------------------------------------------------------------------------- //
// coverityTool_listDefects
// --------------------------------------------------------------------------- //
interface ListInput {
  report?: string;
  limit?: number;
  checker?: string;
  severity?: string;
}

export class ListDefectsTool implements vscode.LanguageModelTool<ListInput> {
  prepareInvocation(options: vscode.LanguageModelToolInvocationPrepareOptions<ListInput>): vscode.PreparedToolInvocation {
    return {
      invocationMessage: `Listing Coverity defects${options.input?.checker ? ` (${options.input.checker})` : ''}…`,
    };
  }

  async invoke(options: vscode.LanguageModelToolInvocationOptions<ListInput>): Promise<vscode.LanguageModelToolResult> {
    try {
      const report = reportFrom(options.input ?? {});
      const limit = Math.max(1, Math.min(Number(options.input?.limit ?? 25), 1000));
      const args = ['list', '--report', report, '--limit', String(limit)];
      if (options.input?.checker) {
        args.push('--checker', options.input.checker);
      }
      if (options.input?.severity) {
        args.push('--severity', options.input.severity);
      }
      const payload = await runBridge<ListPayload>(args);
      const lines = [
        `${payload.returned} of ${payload.total_in_report} defects in ` +
        `\`${path.basename(payload.report)}\`.`,
        '',
        '| CID | Checker | Severity | File | Line | Function |',
        '| --- | --- | --- | --- | --- | --- |',
      ];
      for (const row of payload.defects) {
        lines.push(`| ${row.cid} | ${row.checker} | ${row.severity || '-'} | ` +
          `${row.file || '-'} | ${row.line || 'Various'} | ${row.function || '-'} |`);
      }
      if (payload.returned < payload.total_in_report) {
        lines.push('', 'Raise `limit` or narrow with `checker`/`severity` to see the rest.');
      }
      return textResult(lines.join('\n'));
    } catch (err) {
      return errorResult(err);
    }
  }
}

// --------------------------------------------------------------------------- //
// coverityTool_analyzeDefect
// --------------------------------------------------------------------------- //
interface AnalyzeInput {
  cid?: number;
  report?: string;
  src_root?: string;
  language?: string;
  context_lines?: number;
}

export class AnalyzeDefectTool implements vscode.LanguageModelTool<AnalyzeInput> {
  constructor(private readonly store: FindingsStore) { }

  prepareInvocation(options: vscode.LanguageModelToolInvocationPrepareOptions<AnalyzeInput>): vscode.PreparedToolInvocation {
    return {
      invocationMessage: `Analysing Coverity CID ${options.input?.cid ?? '?'}…`,
    };
  }

  async invoke(options: vscode.LanguageModelToolInvocationOptions<AnalyzeInput>): Promise<vscode.LanguageModelToolResult> {
    try {
      const input = options.input ?? {};
      const cid = requireCid(input);
      const cached = this.store.get(cid);
      if (cached && cached.comment) {
        return textResult(
          formatDefect(cached, true),
          depthWarning(this.store.lastCapabilities));
      }
      const report = reportFrom(input);
      const args = ['context', '--report', report, '--cid', String(cid)];
      const srcRoot = srcRootFrom(input);
      if (srcRoot) {
        args.push('--src', srcRoot);
      }
      const language = (input.language || readSettings().language).toLowerCase();
      args.push('--language', language);
      args.push('--lines', String(Math.max(1, Number(input.context_lines ?? 25))));

      const payload = await runBridge<{ defect: DefectRecord; capabilities?: CapabilitiesPayload }>(args);
      const record = payload.defect;
      if (record.disposition === 'Needs review' && !srcRoot) {
        return textResult(
          formatDefect(record, true),
          '\n_The verdict is "Needs review" and no source root was supplied. Set ' +
          '"coverityTool.sourceRoot" (or pass `src_root`) to the analysed checkout ' +
          'and re-run for a code-anchored verdict._');
      }
      return textResult(formatDefect(record, true));
    } catch (err) {
      return errorResult(err);
    }
  }
}

// --------------------------------------------------------------------------- //
// coverityTool_triageReport
// --------------------------------------------------------------------------- //
interface TriageInput {
  report?: string;
  src_root?: string;
  language?: string;
  limit?: number;
  checker?: string;
  severity?: string;
}

export class TriageReportTool implements vscode.LanguageModelTool<TriageInput> {
  constructor(private readonly store: FindingsStore) { }

  prepareInvocation(options: vscode.LanguageModelToolInvocationPrepareOptions<TriageInput>): vscode.PreparedToolInvocation {
    return {
      invocationMessage: 'Triaging the Coverity report (this can take a while)…',
      confirmationMessages: {
        title: 'Triage Coverity report',
        message: 'Run the Coverity analysis over the report and load the findings into this window?',
      },
    };
  }

  async invoke(options: vscode.LanguageModelToolInvocationOptions<TriageInput>): Promise<vscode.LanguageModelToolResult> {
    try {
      const input = options.input ?? {};
      const report = reportFrom(input);
      const settings = readSettings();
      const payload = await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: 'Coverity: triaging report',
        cancellable: true,
      }, (_progress, token) => runTriage(this.store, {
        report,
        srcRoot: srcRootFrom(input) || undefined,
        language: (input.language || settings.language).toLowerCase(),
        limit: Math.max(1, Math.min(Number(input.limit ?? settings.maxDefects), 5000)),
        checker: input.checker,
        severity: input.severity,
        token,
      }));

      const summary = payload.summary;
      const lines = [
        `**${summary.total} defects** — Bug ${summary.bug}, ` +
        `False positive ${summary.false_positive}, Intentional ${summary.intentional}, ` +
        `Needs review ${summary.needs_review} ` +
        `(mean confidence ${summary.mean_confidence}).`,
        '',
        '| CID | Checker | Disposition | Confidence | Location |',
        '| --- | --- | --- | --- | --- |',
      ];
      for (const record of payload.defects) {
        lines.push(`| ${record.cid} | ${record.checker} | ${record.disposition} | ` +
          `${percent(record.confidence)}% | ` +
          `${record.resolved_file || record.file}:${record.line || '?'} |`);
      }
      lines.push('', 'Per-defect rationale and suggested fixes follow.');
      for (const record of payload.defects) {
        lines.push('', formatDefect(record));
      }
      const needsReview = payload.defects.filter(d => d.disposition === 'Needs review');
      if (needsReview.length) {
        lines.push('', `${needsReview.length} finding(s) are **Needs review** — these are ` +
          'the ones a human has to decide; ask for a specific CID for its full trace.');
      }
      const note = depthWarning(payload.capabilities);
      if (note) {
        lines.push(note);
      }
      lines.push('', `_Findings are also loaded into the Coverity Tool view and the Problems panel` +
        `${payload.written_to ? `, and cached at \`${payload.written_to}\`` : ''}._`);
      return textResult(lines.join('\n'));
    } catch (err) {
      if (isCancellation(err)) {
        return textResult('The triage run was cancelled.');
      }
      return errorResult(err);
    }
  }
}

// --------------------------------------------------------------------------- //
// coverityTool_sourceContext
// --------------------------------------------------------------------------- //
interface SourceInput {
  cid?: number;
  report?: string;
  src_root?: string;
  language?: string;
  context_lines?: number;
}

export class SourceContextTool implements vscode.LanguageModelTool<SourceInput> {
  prepareInvocation(options: vscode.LanguageModelToolInvocationPrepareOptions<SourceInput>): vscode.PreparedToolInvocation {
    return {
      invocationMessage: `Fetching source context for CID ${options.input?.cid ?? '?'}…`,
    };
  }

  async invoke(options: vscode.LanguageModelToolInvocationOptions<SourceInput>): Promise<vscode.LanguageModelToolResult> {
    try {
      const input = options.input ?? {};
      const cid = requireCid(input);
      const args = ['context', '--report', reportFrom(input), '--cid', String(cid)];
      const srcRoot = srcRootFrom(input);
      if (srcRoot) {
        args.push('--src', srcRoot);
      }
      args.push('--language', (input.language || readSettings().language).toLowerCase());
      args.push('--lines', String(Math.max(1, Number(input.context_lines ?? 40))));

      const payload = await runBridge<{ defect: DefectRecord }>(args);
      const record = payload.defect;
      if (!record.source_context?.code) {
        return textResult(
          `No source could be read for CID ${cid}: the report lists the file as ` +
          `\`${record.file}\`, but it was not found locally. ` +
          'Set "coverityTool.sourceRoot" to the analysed checkout and retry.');
      }
      return textResult(
        `CID ${cid} — ${record.checker} at ${record.resolved_file || record.file}:` +
        `${record.line} (${record.disposition})\n\n` +
        '```c\n' + record.source_context.code + '\n```\n\n' +
        `Proposed fix: \`${record.proposed_fix || 'none'}\`\n\n` +
        `Rationale: ${record.comment || ''}`);
    } catch (err) {
      return errorResult(err);
    }
  }
}

// --------------------------------------------------------------------------- //
// Registration
// --------------------------------------------------------------------------- //
export function registerTools(context: vscode.ExtensionContext, store: FindingsStore): void {
  context.subscriptions.push(
    vscode.lm.registerTool('coverityTool_capabilities', new CapabilitiesTool(store)),
    vscode.lm.registerTool('coverityTool_listDefects', new ListDefectsTool()),
    vscode.lm.registerTool('coverityTool_analyzeDefect', new AnalyzeDefectTool(store)),
    vscode.lm.registerTool('coverityTool_triageReport', new TriageReportTool(store)),
    vscode.lm.registerTool('coverityTool_sourceContext', new SourceContextTool()),
  );
}
