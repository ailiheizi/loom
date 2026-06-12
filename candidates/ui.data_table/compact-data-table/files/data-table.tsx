"use client";

type DataTableColumn = {
  key: string;
  header: string;
};

type DataTableProps = {
  columns: DataTableColumn[];
  rows: Record<string, unknown>[];
};

/**
 * 紧凑只读数据表格。保持 {columns, rows} 契约，去掉阴影/圆角，行距更小，
 * 适合密集信息展示（dashboard 小卡片内）。零外部依赖、纯展示无 state。
 */
export function DataTable({ columns, rows }: DataTableProps) {
  return (
    <table className="w-full border-collapse text-left text-xs text-slate-700">
      <thead className="border-b border-slate-300 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        <tr>
          {columns.map((column) => (
            <th key={column.key} scope="col" className="px-2 py-1.5">
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
              className="px-2 py-3 text-center text-slate-400"
            >
              —
            </td>
          </tr>
        ) : (
          rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-b border-slate-100">
              {columns.map((column) => (
                <td key={column.key} className="px-2 py-1">
                  {String(row[column.key] ?? "")}
                </td>
              ))}
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}
