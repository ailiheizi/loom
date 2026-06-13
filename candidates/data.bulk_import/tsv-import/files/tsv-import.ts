type ParsedRow = Record<string, string>;

/**
 * TSV（制表符分隔）批量导入：首行表头，按 \t 切列。
 * 适合从 Excel/Sheets 复制粘贴的数据（TSV 比 CSV 少引号转义问题）。零依赖。
 */
export function parseTsvImport(tsv: string): ParsedRow[] {
  const lines = tsv.split(/\r?\n/).filter((l) => l.trim() !== "");
  if (lines.length === 0) return [];
  const headers = (lines[0] ?? "").split("\t");
  const rows: ParsedRow[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cells = (lines[i] ?? "").split("\t");
    const row: ParsedRow = {};
    headers.forEach((h, idx) => {
      row[h.trim()] = (cells[idx] ?? "").trim();
    });
    rows.push(row);
  }
  return rows;
}
