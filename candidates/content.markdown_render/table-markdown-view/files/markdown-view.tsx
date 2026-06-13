"use client";

interface MarkdownViewProps {
  source: string;
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderInline(text: string): string {
  let out = escapeHtml(text);
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
  return out;
}

/**
 * 支持 GFM 表格的 markdown 渲染。保持 MarkdownView({source}) 契约。
 * 在基础渲染上额外解析 | a | b | 形式的表格。零依赖正则实现。
 */
function toHtml(markdown: string): string {
  const lines = markdown.split("\n");
  const html: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    // 表格：当前行和下一行是 |---| 分隔
    const next = lines[i + 1] ?? "";
    if (/^\s*\|.*\|\s*$/.test(line) && /^\s*\|[\s:|-]+\|\s*$/.test(next)) {
      const parseRow = (r: string): string[] =>
        r.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const headers = parseRow(line);
      html.push("<table><thead><tr>");
      for (const h of headers) html.push(`<th>${renderInline(h)}</th>`);
      html.push("</tr></thead><tbody>");
      i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i] ?? "")) {
        const cells = parseRow(lines[i] ?? "");
        html.push("<tr>");
        for (const cell of cells) html.push(`<td>${renderInline(cell)}</td>`);
        html.push("</tr>");
        i++;
      }
      html.push("</tbody></table>");
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = (heading[1] ?? "").length;
      html.push(`<h${level}>${renderInline(heading[2] ?? "")}</h${level}>`);
      i++;
      continue;
    }
    if (line.trim()) html.push(`<p>${renderInline(line)}</p>`);
    i++;
  }
  return html.join("");
}

export function MarkdownView({ source }: MarkdownViewProps) {
  return <div className="prose" dangerouslySetInnerHTML={{ __html: toHtml(source) }} />;
}
