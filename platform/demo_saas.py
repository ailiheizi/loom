"""完整演示：经 loom.alhz.org 远程组装一个 SaaS 后台，打印每一步的对接过程。
显示：AI 发给 server 的请求 / server 返回 / AI 的输出 / token 计数。
"""
import httpx, json, tiktoken, time

URL = "https://loom.alhz.org/mcp"
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
enc = tiktoken.get_encoding("cl100k_base")
tok = lambda s: len(enc.encode(s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)))


def parse(t):
    for line in t.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])


def sep(title):
    print("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)


ai_out_total = 0
c = httpx.Client(timeout=40)

# ── 握手 ──
sep("步骤 0：连接 loom.alhz.org（MCP 握手）")
t = time.time()
r = c.post(URL, headers=H, json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "demo", "version": "1"}}})
H["mcp-session-id"] = r.headers.get("mcp-session-id")
c.post(URL, headers=H, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
print(f"→ 连上，session={H['mcp-session-id'][:16]}…  耗时 {time.time()-t:.2f}s")

# ── 用户想法 ──
sep("步骤 1：用户想法（AI 把它发给 server）")
idea = {
    "idea_id": "saas-admin-demo", "title": "带 Google 登录的 CRUD SaaS 后台",
    "description": "用户用 Google 登录，对 Project 资源增删改查，表格展示列表，表单创建/编辑，导出。",
    "core_ref": "create-t3-app@7.39.x",
    "capability_intents": [
        {"intent": "用户用 Google 账号登录", "seam_id": "auth.oauth_provider"},
        {"intent": "对 Project 做增删改查", "seam_id": "data.crud_resource"},
        {"intent": "表格展示 Project 列表", "seam_id": "ui.data_table"},
        {"intent": "表单创建/编辑 Project", "seam_id": "ui.form"},
        {"intent": "导出 Project 列表", "seam_id": "report.custom_export"},
    ],
}
idea_json = json.dumps(idea, ensure_ascii=False)
print(f"想法：{idea['title']}（5 个能力 seam）")
print(f"AI→server 发送：loom_propose(idea)  [输入 {tok(idea_json)} tok]")

# ── propose ──
sep("步骤 2：server 返回候选梯度（AI 读它来选）")
t = time.time()
r = c.post(URL, headers=H, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
    "params": {"name": "loom_propose", "arguments": {"idea_json": idea_json}}})
prop = json.loads(parse(r.text)["result"]["content"][0]["text"])
print(f"← server 返回 {len(prop['seams'])} 个 seam 的候选梯度  [{tok(json.dumps(prop,ensure_ascii=False))} tok, 耗时 {time.time()-t:.2f}s]")
for s in prop["seams"]:
    opts = " / ".join(f"{ca['ref']}{'★' if ca.get('recommended') else ''}" for ca in s["candidates"])
    print(f"   {s['seam_id']}: {opts}")

# ── AI 选择（模拟宿主 agent 的输出）──
sep("步骤 3：AI 的输出 —— 逐 seam 选择（这就是省 token 的地方）")
choices = []
ai_choice_text = []
for s in prop["seams"]:
    rec = next((ca["ref"] for ca in s["candidates"] if ca.get("recommended")), s["candidates"][0]["ref"] if s["candidates"] else None)
    if rec:
        choices.append({"seam_id": s["seam_id"], "ref": rec})
        ai_choice_text.append(f"{s['seam_id'].split('.')[-1]}→{rec}")
ai_out = "我选：" + "；".join(ai_choice_text)
print(ai_out)
n = tok(ai_out); ai_out_total += n
print(f"[AI output: {n} tok]  ← 全部 5 个选择只用了这么多")

# ── plan ──
sep("步骤 4：server 把选择拼成 plan")
t = time.time()
r = c.post(URL, headers=H, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
    "params": {"name": "loom_plan_from_choices", "arguments": {"idea_json": idea_json, "choices_json": json.dumps(choices)}}})
plan = json.loads(parse(r.text)["result"]["content"][0]["text"])
print(f"← plan 含 {len(plan['seams'])} 个决策  [耗时 {time.time()-t:.2f}s]")
for d in plan["seams"]:
    print(f"   {d['seam_id']}: {d['action']} → {d.get('ref')}")

# ── get_files ──
sep("步骤 5：server 返回完整项目文件（AI 不用自己写代码）")
t = time.time()
r = c.post(URL, headers=H, json={"jsonrpc": "2.0", "id": 4, "method": "tools/call",
    "params": {"name": "loom_get_files", "arguments": {"plan_json": json.dumps(plan)}}})
gf = json.loads(parse(r.text)["result"]["content"][0]["text"])
total_code_tok = sum(tok(f["content"]) for f in gf["files"])
print(f"← server 返回 {len(gf['files'])} 个文件，共 {total_code_tok} tok 代码  [耗时 {time.time()-t:.2f}s]")
print(f"   deps: {gf['deps']}  env: {gf['env_vars']}  prisma: {gf['prisma_models']}")
loom_landed = [f["path"] for f in gf["files"] if any(k in f["path"] for k in
    ["providers/google", "routers/project", "data-table", "form-view", "export"])]
print(f"   选中组件落盘：{loom_landed}")

# ── 总账 ──
sep("总账：这次 SaaS 后台组装")
print(f"AI 总输出（5 个选择）: {ai_out_total} tok")
print(f"对比：若 AI 从零写这些组件，需输出约 {total_code_tok} tok 的代码")
print(f"→ AI output 省约 {(1-ai_out_total/total_code_tok)*100:.0f}%（{total_code_tok} → {ai_out_total}）")
print(f"\n用户拿到：{len(gf['files'])} 文件的完整 t3 项目，写盘 + pnpm install + 填 .env 即可跑")
c.close()
