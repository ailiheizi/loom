"use client";

import { useState } from "react";

type FormField = {
  name: string;
  label: string;
  required?: boolean;
};

type FormViewProps = {
  fields: FormField[];
  onSubmit: (data: Record<string, string>) => void;
  submitLabel?: string;
};

/**
 * 带必填校验的受控表单。field.required 的字段为空时阻止提交并显示错误。
 * 零外部依赖。适合需要基础校验的创建/编辑场景。
 */
export function FormView({ fields, onSubmit, submitLabel = "提交" }: FormViewProps) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  function setField(name: string, value: string) {
    setValues((prev) => ({ ...prev, [name]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const next: Record<string, string> = {};
    for (const field of fields) {
      if (field.required && !(values[field.name] ?? "").trim()) {
        next[field.name] = `${field.label}不能为空`;
      }
    }
    setErrors(next);
    if (Object.keys(next).length === 0) {
      onSubmit(values);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {fields.map((field) => (
        <label key={field.name} className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-slate-700">
            {field.label}
            {field.required ? <span className="text-red-500"> *</span> : null}
          </span>
          <input
            type="text"
            value={values[field.name] ?? ""}
            onChange={(e) => setField(field.name, e.target.value)}
            className="rounded border border-slate-300 px-3 py-2 outline-none focus:border-slate-400"
          />
          {errors[field.name] ? (
            <span className="text-xs text-red-500">{errors[field.name]}</span>
          ) : null}
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
