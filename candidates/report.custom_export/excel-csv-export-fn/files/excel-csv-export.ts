type ExportRow = Record<string, string | number | boolean | null | undefined>;

function escapeCell(value: string | number | boolean | null | undefined): string {
  const str = value === null || value === undefined ? "" : String(value);
  if (/[",\n\r]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

// UTF-8 BOM：让 Excel 正确识别中文等多字节字符编码，避免乱码
const BOM = "﻿";

/**
 * Excel 友好的 CSV 导出。保持 (rows, columns?) 契约，输出带 UTF-8 BOM 的 CSV，
 * 解决 Excel 打开中文 CSV 乱码问题。零依赖。
 */
export function rowsToExcelCsv(rows: ExportRow[], columns?: string[]): string {
  const first = rows[0];
  if (!first) return BOM;
  const cols = columns ?? Object.keys(first);
  const header = cols.map(escapeCell).join(",");
  const body = rows
    .map((row) => cols.map((c) => escapeCell(row[c])).join(","))
    .join("\r\n");
  return `${BOM}${header}\r\n${body}`;
}

export function toExcelCsvBlob(rows: ExportRow[], columns?: string[]): Blob {
  return new Blob([rowsToExcelCsv(rows, columns)], {
    type: "text/csv;charset=utf-8;",
  });
}
