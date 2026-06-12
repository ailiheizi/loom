type ExportRow = Record<string, string | number | boolean | null | undefined>;

/**
 * JSON 导出。保持与 csv-export-fn 同构的 (rows, columns?) 契约，
 * 输出 pretty-printed JSON 字符串 / Blob。零依赖。
 */
export function rowsToJson(rows: ExportRow[], columns?: string[]): string {
  if (!columns) return JSON.stringify(rows, null, 2);
  const projected = rows.map((row) => {
    const obj: ExportRow = {};
    for (const c of columns) {
      obj[c] = row[c];
    }
    return obj;
  });
  return JSON.stringify(projected, null, 2);
}

export function toJsonBlob(rows: ExportRow[], columns?: string[]): Blob {
  return new Blob([rowsToJson(rows, columns)], {
    type: "application/json;charset=utf-8;",
  });
}
