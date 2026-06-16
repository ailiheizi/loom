"""实测：用 loom.alhz.org 远程 server 做一个项目，省多少 token。

测的是宿主 AI 的 OUTPUT token（最贵的部分）：
- 用 Loom：AI 看 propose 候选 → 输出"选哪个"（极小）；代码由 get_files 返回，AI 不生成
- 不用 Loom：AI 从零写每个组件文件（auth/crud/table…），全是 AI output

用真 tiktoken(cl100k_base) 计 token，经公网真实调用。
"""
import httpx, json, tiktoken

URL = "https://loom.alhz.org/mcp"
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
enc = tiktoken.get_encoding("cl100k_base")
tok = lambda s: len(enc.encode(s))


def parse(t):
    for line in t.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])


with httpx.Client(timeout=40) as c:
    r = c.post(URL, headers=H, json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "bench", "version": "1"}}})
    H["mcp-session-id"] = r.headers.get("mcp-session-id")
    c.post(URL, headers=H, json={"jsonrpc": "2.0", "method": "notifications/initialized"})

    # 1. propose：server 返回候选梯度（这是 AI 的 INPUT，读它来选）
    idea = open("../ideas/saas-admin-with-google-auth.json", encoding="utf-8").read()
    r = c.post(URL, headers=H, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "loom_propose", "arguments": {"idea_json": idea}}})
    prop = parse(r.text)["result"]["content"][0]["text"]

    # 2. get_files：拿到选中候选的真实代码（= AI 免于生成的代码量）
    plan = json.dumps({"idea_id": "saas", "core_ref": "create-t3-app@7.39.x", "seams": [
        {"seam_id": "auth.oauth_provider", "action": "pick", "ref": "google-oauth", "confidence": 1, "why": "x"},
        {"seam_id": "data.crud_resource", "action": "pick", "ref": "project-crud-router", "confidence": 1, "why": "x"},
        {"seam_id": "ui.data_table", "action": "pick", "ref": "simple-data-table", "confidence": 1, "why": "x"},
    ], "synthesized": [], "budget": {"input_tok": 0, "output_tok": 0}})
    r = c.post(URL, headers=H, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "loom_get_files", "arguments": {"plan_json": plan}}})
    gf = json.loads(parse(r.text)["result"]["content"][0]["text"])

# 选中候选的代码（AI 不用自己写的）
cand_keys = ["providers/google.ts", "routers/project.ts", "_components/data-table.tsx"]
cand_files = [f for f in gf["files"] if any(k in f["path"] for k in cand_keys)]
cand_code = "\n".join(f["content"] for f in cand_files)

# ── 用 Loom：AI 的 output = 选择决策（3 个 seam，每个就是 "选 X 因为 Y"）
loom_output = '选择：auth→google-oauth（精确匹配Google登录）；crud→project-crud-router（专为Project的完整CRUD）；table→simple-data-table（零依赖）。'
loom_out_tok = tok(loom_output)

# ── 不用 Loom：AI 要从零写这些组件代码（output = 这些代码本身）
fromzero_out_tok = tok(cand_code)

print("=== 实测：经 loom.alhz.org 做一个 SaaS 后台（auth+CRUD+表格 3 组件）===")
print(f"propose 候选梯度大小（AI 读的 input）: {tok(prop)} tok")
print(f"get_files 返回代码: {sum(tok(f['content']) for f in cand_files)} tok（{len(cand_files)} 个候选文件）")
print()
print(f"【用 Loom】AI output（只输出选择）: {loom_out_tok} tok")
print(f"【不用 Loom】AI output（从零写这 3 个组件）: {fromzero_out_tok} tok")
saved = (1 - loom_out_tok / fromzero_out_tok) * 100
print(f"→ AI output 省: {saved:.0f}%（{fromzero_out_tok} → {loom_out_tok}）")
print()
print("注：只算 3 个 pick 组件。真实项目组件更多，省得更多；但从零写也可能更省字(AI偷工)，故此为量级参考。")
