type ExportRow = Record<string, string | number | boolean | null | undefined>;

function escapeMdCell(value: string | number | boolean | null | undefined): string {
  const str = value === null || value === undefined ? "" : String(value);
  // Markdown 表格：转义竖线，换行替换为空格
  return str.replace(/\|/g, "\\|").replace(/[\r\n]+/g, " ");
}

/**
 * Markdown 表格导出。保持 (rows, columns?) 契约，产出 GFM 表格字符串 / Blob。
 * 适合贴进 README / issue / 文档。零依赖。
 */
export function rowsToMarkdown(rows: ExportRow[], columns?: string[]): string {
  const first = rows[0];
  if (!first) return "";
  const cols = columns ?? Object.keys(first);
  const header = `| ${cols.map(escapeMdCell).join(" | ")} |`;
  const divider = `| ${cols.map(() => "---").join(" | ")} |`;
  const body = rows
    .map((row) => `| ${cols.map((c) => escapeMdCell(row[c])).join(" | ")} |`)
    .join("\n");
  return `${header}\n${divider}\n${body}`;
}

export function toMarkdownBlob(rows: ExportRow[], columns?: string[]): Blob {
  return new Blob([rowsToMarkdown(rows, columns)], {
    type: "text/markdown;charset=utf-8;",
  });
}
