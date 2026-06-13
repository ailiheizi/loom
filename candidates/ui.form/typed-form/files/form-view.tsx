"use client";

import { useState } from "react";

type FormField = {
  name: string;
  label: string;
  type?: "text" | "textarea" | "select";
  options?: string[];
};

type FormViewProps = {
  fields: FormField[];
  onSubmit: (data: Record<string, string>) => void;
  submitLabel?: string;
};

/**
 * 多字段类型表单：支持 text / textarea / select。保持 {fields, onSubmit} 契约。
 * 零外部依赖。适合字段类型多样的实体编辑（如带描述、状态下拉的资源）。
 */
export function FormView({ fields, onSubmit, submitLabel = "提交" }: FormViewProps) {
  const [values, setValues] = useState<Record<string, string>>({});

  function setField(name: string, value: string) {
    setValues((prev) => ({ ...prev, [name]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit(values);
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {fields.map((field) => {
        const value = values[field.name] ?? "";
        const cls = "rounded border border-slate-300 px-3 py-2 outline-none focus:border-slate-400";
        return (
          <label key={field.name} className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">{field.label}</span>
            {field.type === "textarea" ? (
              <textarea
                value={value}
                onChange={(e) => setField(field.name, e.target.value)}
                className={cls}
                rows={4}
              />
            ) : field.type === "select" ? (
              <select
                value={value}
                onChange={(e) => setField(field.name, e.target.value)}
                className={cls}
              >
                <option value="">请选择…</option>
                {(field.options ?? []).map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={value}
                onChange={(e) => setField(field.name, e.target.value)}
                className={cls}
              />
            )}
          </label>
        );
      })}
      <button
        type="submit"
        className="rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
      >
        {submitLabel}
      </button>
    </form>
  );
}
