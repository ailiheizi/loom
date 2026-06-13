"use client";

type DetailField = {
  key: string;
  label: string;
};

type DetailViewProps = {
  data: Record<string, unknown>;
  fields?: DetailField[];
  title?: string;
};

/**
 * 卡片式详情：带标题的卡片，字段以 label/value 堆叠展示。保持 {data, fields, title} 契约。
 * 零外部依赖。适合单条资源的展示卡片。
 */
export function DetailView({ data, fields, title }: DetailViewProps) {
  const rows: DetailField[] =
    fields ?? Object.keys(data).map((k) => ({ key: k, label: k }));

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      {title ? <h2 className="mb-4 text-lg font-semibold text-slate-800">{title}</h2> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        {rows.map((field) => (
          <div key={field.key} className="flex flex-col gap-1">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
              {field.label}
            </span>
            <span className="text-sm text-slate-800">{String(data[field.key] ?? "")}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
