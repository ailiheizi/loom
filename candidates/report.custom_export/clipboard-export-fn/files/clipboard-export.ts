type ExportRow = Record<string, string | number | boolean | null | undefined>;

function escapeCell(value: string | number | boolean | null | undefined): string {
  const str = value === null || value === undefined ? "" : String(value);
  if (/[",\n\r]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

/**
 * 复制到剪贴板的导出。保持 (rows, columns?) 契约，产出 CSV 文本，
 * copyToClipboard 用浏览器原生 navigator.clipboard 写入。零依赖。
 */
export function rowsToClipboardText(rows: ExportRow[], columns?: string[]): string {
  const first = rows[0];
  if (!first) return "";
  const cols = columns ?? Object.keys(first);
  const header = cols.map(escapeCell).join(",");
  const body = rows
    .map((row) => cols.map((c) => escapeCell(row[c])).join(","))
    .join("\n");
  return `${header}\n${body}`;
}

export async function copyToClipboard(rows: ExportRow[], columns?: string[]): Promise<boolean> {
  const text = rowsToClipboardText(rows, columns);
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
