type ExportRow = Record<string, string | number | boolean | null | undefined>;

function escapeCell(value: string | number | boolean | null | undefined): string {
  const str =
    value === null || value === undefined ? "" : String(value);
  if (/[",\n\r]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

export function rowsToCsv(rows: ExportRow[], columns?: string[]): string {
  const first = rows[0];
  if (!first) return "";
  const cols = columns ?? Object.keys(first);
  const header = cols.map(escapeCell).join(",");
  const body = rows
    .map((row) => cols.map((c) => escapeCell(row[c])).join(","))
    .join("\n");
  return `${header}\n${body}`;
}

export function toCsvBlob(rows: ExportRow[], columns?: string[]): Blob {
  return new Blob([rowsToCsv(rows, columns)], {
    type: "text/csv;charset=utf-8;",
  });
}
