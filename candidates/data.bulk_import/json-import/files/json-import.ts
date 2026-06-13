type ParsedRow = Record<string, string>;

/**
 * JSON 数组批量导入：解析 JSON 数组，每项规整为 Record<string,string>（值转字符串）。
 * 适合从 API/导出的 JSON 批量导入。零依赖。非数组或非法 JSON 返回空数组。
 */
export function parseJsonImport(json: string): ParsedRow[] {
  let data: unknown;
  try {
    data = JSON.parse(json);
  } catch {
    return [];
  }
  if (!Array.isArray(data)) return [];
  const rows: ParsedRow[] = [];
  for (const item of data) {
    if (item === null || typeof item !== "object") continue;
    const row: ParsedRow = {};
    for (const [k, v] of Object.entries(item as Record<string, unknown>)) {
      row[k] = v === null || v === undefined ? "" : String(v);
    }
    rows.push(row);
  }
  return rows;
}
