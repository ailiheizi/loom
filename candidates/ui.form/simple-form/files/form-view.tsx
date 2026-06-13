"use client";

import { useState } from "react";

type FormField = {
  name: string;
  label: string;
};

type FormViewProps = {
  fields: FormField[];
  onSubmit: (data: Record<string, string>) => void;
  submitLabel?: string;
};

/**
 * 基础受控表单。每个 field 渲染一个 text input，提交时回调收集到的 Record。
 * 零外部依赖（不引 react-hook-form）。配合 data.crud_resource 的 create/update。
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
      {fields.map((field) => (
        <label key={field.name} className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-slate-700">{field.label}</span>
          <input
            type="text"
            value={values[field.name] ?? ""}
            onChange={(e) => setField(field.name, e.target.value)}
            className="rounded border border-slate-300 px-3 py-2 outline-none focus:border-slate-400"
          />
        </label>
      ))}
      <button
        type="submit"
        className="rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
      >
        {submitLabel}
      </button>
    </form>
  );
}
