/**
 * Anthropic 客户端封装：统一模型名、base URL、token 计量。
 */
import Anthropic from "@anthropic-ai/sdk";

export const MODEL = process.env.LOOM_MODEL ?? "claude-sonnet-4-6";

export interface LlmUsage {
  input_tok: number;
  output_tok: number;
}

let _client: Anthropic | null = null;

export function client(): Anthropic {
  if (!_client) {
    _client = new Anthropic({
      apiKey: process.env.ANTHROPIC_API_KEY,
      baseURL: process.env.ANTHROPIC_BASE_URL,
    });
  }
  return _client;
}

/** 单轮文本补全，返回首个 text block 与 usage。 */
export async function complete(
  system: string,
  userMsg: string,
  maxTokens = 4096,
): Promise<{ text: string; usage: LlmUsage }> {
  const resp = await client().messages.create({
    model: MODEL,
    max_tokens: maxTokens,
    system,
    messages: [{ role: "user", content: userMsg }],
  });
  const text = resp.content
    .filter((b): b is Anthropic.TextBlock => b.type === "text")
    .map((b) => b.text)
    .join("");
  return {
    text,
    usage: { input_tok: resp.usage.input_tokens, output_tok: resp.usage.output_tokens },
  };
}

/** 从 AI 回复里抽取代码块内容（去掉 ```lang fences）。 */
export function extractCode(text: string): string {
  const fence = text.match(/```(?:[a-zA-Z]+)?\n([\s\S]*?)```/);
  return fence ? fence[1].trim() : text.trim();
}
