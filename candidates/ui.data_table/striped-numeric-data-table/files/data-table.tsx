"use client";

type DataTableColumn = {
  key: string;
  header: string;
};

type DataTableProps = {
  columns: DataTableColumn[];
  rows: Record<string, unknown>[];
};

/** 判断一个单元格值是否为数字（用于右对齐）。 */
function isNumeric(value: unknown): boolean {
  if (typeof value === "number") return true;
  if (typeof value === "string" && value.trim() !== "") {
    return !Number.isNaN(Number(value));
  }
  return false;
}

/**
 * 斑马纹数据表格，数字列自动右对齐。保持 {columns, rows} 契约。
 * 隔行底色 + 数字右对齐，适合财务/报表类只读展示。零外部依赖。
 */
export function DataTable({ columns, rows }: DataTableProps) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
      <table className="min-w-full text-left text-sm text-slate-700">
        <thead className="bg-slate-100 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className="px-4 py-3">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length || 1}
                className="px-4 py-6 text-center text-sm text-slate-500"
              >
                No data available.
              </td>
            </tr>
          ) : (
            rows.map((row, rowIndex) => (
              <tr key={rowIndex} className={rowIndex % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                {columns.map((column) => {
                  const value = row[column.key];
                  return (
                    <td
                      key={column.key}
                      className={
                        isNumeric(value)
                          ? "px-4 py-2.5 text-right tabular-nums"
                          : "px-4 py-2.5"
                      }
                    >
                      {String(value ?? "")}
                    </td>
                  );
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
