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

type SortDir = "asc" | "desc";

/**
 * 可排序数据表格。保持 {columns, rows} 契约，点击表头在 asc/desc/无序间循环。
 * 用 String() 比较，对混合类型安全。零外部依赖（不引 tanstack）。
 */
export function DataTable({ columns, rows }: DataTableProps) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const sortedRows = useMemo(() => {
    if (sortKey === null) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = String(a[sortKey] ?? "");
      const bv = String(b[sortKey] ?? "");
      const cmp = av.localeCompare(bv, undefined, { numeric: true });
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  function toggleSort(key: string) {
    if (sortKey !== key) {
      setSortKey(key);
      setSortDir("asc");
    } else if (sortDir === "asc") {
      setSortDir("desc");
    } else {
      setSortKey(null);
    }
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
      <table className="min-w-full divide-y divide-slate-200 text-left text-sm text-slate-700">
        <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            {columns.map((column) => {
              const active = sortKey === column.key;
              const arrow = active ? (sortDir === "asc" ? " ▲" : " ▼") : "";
              return (
                <th key={column.key} scope="col" className="px-4 py-3">
                  <button
                    type="button"
                    onClick={() => toggleSort(column.key)}
                    className="font-semibold uppercase tracking-wide hover:text-slate-800"
                  >
                    {column.header}
                    {arrow}
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {sortedRows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length || 1}
                className="px-4 py-6 text-center text-sm text-slate-500"
              >
                No data available.
              </td>
            </tr>
          ) : (
            sortedRows.map((row, rowIndex) => (
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
  );
}
