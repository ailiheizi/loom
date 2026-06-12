"use client";

import { useMemo, useState } from "react";

type DataTableColumn = {
  key: string;
  header: string;
};

type DataTableProps = {
  columns: DataTableColumn[];
  rows: Record<string, unknown>[];
};

/**
 * 带全局文本筛选的数据表格。保持 {columns, rows} 契约，顶部一个搜索框，
 * 跨所有列做大小写不敏感子串匹配。零外部依赖。
 */
export function DataTable({ columns, rows }: DataTableProps) {
  const [query, setQuery] = useState<string>("");

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length === 0) return rows;
    return rows.filter((row) =>
      columns.some((column) =>
        String(row[column.key] ?? "")
          .toLowerCase()
          .includes(q),
      ),
    );
  }, [rows, columns, query]);

  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-4 py-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter…"
          className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 outline-none focus:border-slate-400"
        />
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm text-slate-700">
          <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              {columns.map((column) => (
                <th key={column.key} scope="col" className="px-4 py-3">
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {filteredRows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length || 1}
                  className="px-4 py-6 text-center text-sm text-slate-500"
                >
                  No matching rows.
                </td>
              </tr>
            ) : (
              filteredRows.map((row, rowIndex) => (
                <tr key={rowIndex} className="hover:bg-slate-50">
                  {columns.map((column) => (
                    <td key={column.key} className="px-4 py-3 align-top">
                      {String(row[column.key] ?? "")}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
