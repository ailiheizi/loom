"use client";

import { useState } from "react";

type DataTableColumn = {
  key: string;
  header: string;
};

type DataTableProps = {
  columns: DataTableColumn[];
  rows: Record<string, unknown>[];
};

/**
 * 可多选行的数据表格。保持 {columns, rows} 契约，左侧加复选框列，
 * 支持全选/单选，顶部显示已选计数。零外部依赖。
 */
export function DataTable({ columns, rows }: DataTableProps) {
  const [selected, setSelected] = useState<Set<number>>(new Set());

  function toggleRow(index: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) =>
      prev.size === rows.length ? new Set() : new Set(rows.map((_, i) => i)),
    );
  }

  const allChecked = rows.length > 0 && selected.size === rows.length;

  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-4 py-2 text-xs text-slate-500">
        {selected.size} selected
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm text-slate-700">
          <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th scope="col" className="px-4 py-3">
                <input
                  type="checkbox"
                  checked={allChecked}
                  onChange={toggleAll}
                  aria-label="Select all rows"
                />
              </th>
              {columns.map((column) => (
                <th key={column.key} scope="col" className="px-4 py-3">
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={(columns.length || 1) + 1}
                  className="px-4 py-6 text-center text-sm text-slate-500"
                >
                  No data available.
                </td>
              </tr>
            ) : (
              rows.map((row, rowIndex) => (
                <tr
                  key={rowIndex}
                  className={selected.has(rowIndex) ? "bg-sky-50" : "hover:bg-slate-50"}
                >
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selected.has(rowIndex)}
                      onChange={() => toggleRow(rowIndex)}
                      aria-label={`Select row ${rowIndex + 1}`}
                    />
                  </td>
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
