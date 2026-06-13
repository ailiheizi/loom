"use client";

type DetailField = {
  key: string;
  label: string;
};

type DetailViewProps = {
  data: Record<string, unknown>;
  fields?: DetailField[];
};

/**
 * 字段列表式详情：定义列表（dl/dt/dd）逐字段展示。保持 {data, fields} 契约。
 * fields 省略时展示 data 的所有键。零外部依赖。
 */
export function DetailView({ data, fields }: DetailViewProps) {
  const rows: DetailField[] =
    fields ?? Object.keys(data).map((k) => ({ key: k, label: k }));

  return (
    <dl className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
      {rows.map((field) => (
        <div key={field.key} className="flex px-4 py-3 text-sm">
          <dt className="w-40 shrink-0 font-medium text-slate-500">{field.label}</dt>
          <dd className="text-slate-800">{String(data[field.key] ?? "")}</dd>
        </div>
      ))}
    </dl>
  );
}
