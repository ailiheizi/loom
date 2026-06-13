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
 * 支持 ``` 代码块（fenced code）的 markdown 渲染。保持 MarkdownView({source}) 契约。
 * 代码块内不做 inline 解析、原样转义。零依赖。
 */
function toHtml(markdown: string): string {
  const lines = markdown.split("\n");
  const html: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    if (/^```/.test(line)) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i] ?? "")) {
        code.push(escapeHtml(lines[i] ?? ""));
        i++;
      }
      i++; // 跳过结束 ```
      html.push(`<pre><code>${code.join("\n")}</code></pre>`);
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
