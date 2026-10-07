/**
 * dispositions.ts — the push-ready CSV, built the way the engine builds it.
 *
 * The desktop Coverity Findings Analyzer can load a dispositions CSV on its
 * Push page, and it matches columns by name. This module therefore emits
 * *exactly* the same header, in the same order, as the engine's
 * `write_dispositions_csv` (vscode_bridge.py): if the two ever diverge, a file
 * exported from VS Code is silently unusable for pushing — which is the whole
 * point of exporting it.
 *
 * Kept free of any `vscode` import so it can be compiled and executed directly
 * by the tests (tests/test_extension_export.py).
 */
import type { DefectRecord } from './bridge';

/** Column order shared with `vscode_bridge.DISPOSITIONS_CSV_HEADER`. */
export const DISPOSITIONS_HEADER = [
  'CID', 'Checker', 'Type', 'Severity', 'Action', 'File', 'Line', 'Function',
  'Classification', 'Comment', 'Fix', 'Timestamp', 'Category',
] as const;

/**
 * The disposition → Connect action mapping used by the push tooling
 * (`coverity_push.default_action_for_classification`, which invokes Coverity's
 * own action vocabulary).
 */
export function connectAction(disposition: string): string {
  switch ((disposition || '').trim().toLowerCase()) {
    case 'bug':
      return 'Fix Required';
    case 'false positive':
    case 'intentional':
      return 'Ignore';
    case 'needs review':
    default:
      return 'Undecided';
  }
}

function quote(value: unknown): string {
  return `"${String(value ?? '').replace(/"/g, '""')}"`;
}

/**
 * Render triage records as a dispositions CSV the desktop app can push.
 *
 * `now` is injectable so tests are deterministic.
 */
export function dispositionsCsv(
  records: readonly DefectRecord[],
  now: Date = new Date(),
): string {
  const timestamp = formatTimestamp(now);
  const rows = records.map(record => {
    const classification = (record.disposition || 'Needs review').trim();
    return [
      record.cid,
      record.checker,
      record.type,
      record.severity,
      connectAction(classification),
      record.resolved_file || record.file,
      record.line,
      record.function,
      classification,
      (record.comment || '').trim(),
      (record.proposed_fix || '').trim(),
      timestamp,
      record.category,
    ].map(quote).join(',');
  });
  return [DISPOSITIONS_HEADER.map(quote).join(','), ...rows].join('\r\n') + '\r\n';
}

/** `YYYY-MM-DD HH:MM:SS`, matching the engine's stamp format. */
function formatTimestamp(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
    + `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}
