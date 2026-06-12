/**
 * LLM 客户端封装：统一模型名、token 计量。
 *
 * 双 provider：
 *  - LOOM_LLM_PROVIDER=deepseek（或任何 OpenAI 兼容）→ 走 fetch /v1/chat/completions，
 *    复用 LOOM_LLM_API_KEY / LOOM_LLM_BASE_URL / LOOM_LLM_MODEL（与 platform 侧一致）。
 *  - 否则 → Anthropic SDK（ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL / LOOM_MODEL）。
 * complete() 签名不变，三处调用方（repair generate/fix、fromZero）无需改动。
 */
import Anthropic from "@anthropic-ai/sdk";

export const MODEL = process.env.LOOM_MODEL ?? "claude-sonnet-4-6";

export interface LlmUsage {
  input_tok: number;
  output_tok: number;
}

function useOpenAICompat(): boolean {
  const p = (process.env.LOOM_LLM_PROVIDER ?? "").toLowerCase();
  return p === "deepseek" || p === "openai";
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

/** OpenAI 兼容端点（deepseek）单轮补全，用原生 fetch，零新依赖。 */
async function completeOpenAI(
  system: string,
  userMsg: string,
  maxTokens: number,
): Promise<{ text: string; usage: LlmUsage }> {
  const base = (process.env.LOOM_LLM_BASE_URL ?? "https://api.deepseek.com").replace(/\/$/, "");
  const model = process.env.LOOM_LLM_MODEL ?? "deepseek-chat";
  const key = process.env.LOOM_LLM_API_KEY;
  if (!key) throw new Error("缺 LOOM_LLM_API_KEY（OpenAI 兼容 provider 需要）");

  const resp = await fetch(`${base}/v1/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${key}`,
    },
    body: JSON.stringify({
      model,
      max_tokens: maxTokens,
      messages: [
        { role: "system", content: system },
        { role: "user", content: userMsg },
      ],
    }),
  });
  if (!resp.ok) {
    throw new Error(`LLM HTTP ${resp.status}: ${(await resp.text()).slice(0, 300)}`);
  }
  const data = (await resp.json()) as {
    choices: { message: { content: string } }[];
    usage?: { prompt_tokens?: number; completion_tokens?: number };
  };
  const text = data.choices[0]?.message?.content ?? "";
  return {
    text,
    usage: {
      input_tok: data.usage?.prompt_tokens ?? 0,
      output_tok: data.usage?.completion_tokens ?? 0,
    },
  };
}

/** 单轮文本补全，返回文本与 usage。provider 由 LOOM_LLM_PROVIDER 决定。 */
export async function complete(
  system: string,
  userMsg: string,
  maxTokens = 4096,
): Promise<{ text: string; usage: LlmUsage }> {
  if (useOpenAICompat()) {
    return completeOpenAI(system, userMsg, maxTokens);
  }
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
