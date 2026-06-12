type ExportRow = Record<string, string | number | boolean | null | undefined>;

function escapeTsvCell(value: string | number | boolean | null | undefined): string {
  const str = value === null || value === undefined ? "" : String(value);
  // TSV：制表符/换行用空格替换，避免破坏列对齐
  return str.replace(/[\t\r\n]+/g, " ");
}

/**
 * TSV（制表符分隔）导出。保持 (rows, columns?) 契约。
 * Excel/Sheets 粘贴友好，比 CSV 少引号转义问题。零依赖。
 */
export function rowsToTsv(rows: ExportRow[], columns?: string[]): string {
  const first = rows[0];
  if (!first) return "";
  const cols = columns ?? Object.keys(first);
  const header = cols.map(escapeTsvCell).join("\t");
  const body = rows
    .map((row) => cols.map((c) => escapeTsvCell(row[c])).join("\t"))
    .join("\n");
  return `${header}\n${body}`;
}

export function toTsvBlob(rows: ExportRow[], columns?: string[]): Blob {
  return new Blob([rowsToTsv(rows, columns)], {
    type: "text/tab-separated-values;charset=utf-8;",
  });
}
