"use client";

interface MarkdownViewProps {
  source: string;
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/**
 * 极简 markdown 渲染：只处理标题与段落，不解析 inline 标记。保持 MarkdownView({source}) 契约。
 * 最轻量、最安全（不渲染任意 inline HTML），适合可信度低或只需基础排版的场景。零依赖。
 */
function toHtml(markdown: string): string {
  const html: string[] = [];
  for (const line of markdown.split("\n")) {
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = (heading[1] ?? "").length;
      html.push(`<h${level}>${escapeHtml(heading[2] ?? "")}</h${level}>`);
    } else if (line.trim()) {
      html.push(`<p>${escapeHtml(line)}</p>`);
    }
  }
  return html.join("");
}

export function MarkdownView({ source }: MarkdownViewProps) {
  return <div className="prose" dangerouslySetInnerHTML={{ __html: toHtml(source) }} />;
}
