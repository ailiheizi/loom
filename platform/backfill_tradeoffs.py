"""一次性：给候选 meta.json 的 meta_loom 回填 tradeoffs（架构取舍）字段。

第二步「候选级梯度呈现」配套：目标用户是架构师，挑候选时要看依赖/复杂度/适用场景。
只在 registry_item.meta_loom 里加 tradeoffs，不动任何其他字段。幂等。

用法：cd platform && uv run python backfill_tradeoffs.py [--dry-run]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CAND = ROOT / "candidates"

# 候选 ref → tradeoffs（基于实际源码理解写，不瞎编能力）
TRADEOFFS: dict[str, str] = {
    # ── ui.data_table ──
    "simple-data-table": "零外部依赖，原生 table。功能基础（无排序/分页/筛选）。适合快速展示小数据量，不适合大数据或需交互的场景。",
    "tanstack-data-table": "依赖 @tanstack/react-table（需装包），支持排序等高级能力。适合复杂交互表格，代价是引入运行时依赖与学习成本。",
    "paginated-data-table": "零依赖，客户端分页（可选 pageSize）。适合中等数据量分页浏览；纯客户端分页，超大数据集仍需服务端分页。",
    "sortable-data-table": "零依赖，点击表头排序（localeCompare 数字感知）。适合需排序但不想引 tanstack 的场景；排序在客户端，大数据量有性能上限。",
    "filterable-data-table": "零依赖，顶部全局文本筛选（跨列子串匹配）。适合带搜索的列表；仅文本包含匹配，无高级筛选条件。",
    "compact-data-table": "零依赖，紧凑只读（小行距、无阴影圆角）。适合 dashboard 卡片内密集展示；纯展示无交互。",
    "selectable-data-table": "零依赖，多选行（复选框列 + 全选 + 已选计数）。适合批量操作场景；选择状态在组件内，需自行接批量动作。",
    "striped-numeric-data-table": "零依赖，斑马纹 + 数字列自动右对齐。适合财务/报表只读展示；按值类型判断对齐，纯展示无交互。",
    # ── report.custom_export ──
    "csv-export-fn": "零依赖，浏览器原生 CSV（处理逗号/引号/换行转义）。通用导出首选；Excel 打开中文可能乱码（用 excel-csv 版）。",
    "excel-csv-export-fn": "零依赖，带 UTF-8 BOM 的 CSV，解决 Excel 中文乱码。面向 Excel 用户首选；纯文本/程序消费场景用普通 csv 即可。",
    "json-export-fn": "零依赖，pretty JSON + 列投影。适合程序间数据交换/调试；不适合给非技术用户。",
    "tsv-export-fn": "零依赖，制表符分隔。Excel/Sheets 粘贴友好、少引号转义问题；字段内含制表符会被替换为空格。",
    "clipboard-export-fn": "零依赖，复制 CSV 到剪贴板（navigator.clipboard）。适合快速复制粘贴；依赖浏览器剪贴板权限，需 https/用户手势。",
    "markdown-export-fn": "零依赖，GFM 表格。适合贴进 README/issue/文档；不适合数据量大或需机器解析的场景。",
    # ── auth.oauth_provider ──
    "google-oauth": "NextAuth Google provider，接 authConfig.providers[]。覆盖最广的消费级登录；需配 Google OAuth 凭据。",
    "github-oauth": "NextAuth GitHub provider。面向开发者/技术产品的登录首选；非技术用户覆盖不如 Google。",
    "credentials-auth": "NextAuth Credentials（账号密码）。无第三方依赖、自主可控；需自行管理密码安全/哈希，安全责任更重。",
    # ── data.crud_resource ──
    "project-crud-router": "tRPC router，专为 Project 资源的完整 CRUD（list/get/create/update/delete）。需对应 prisma model；最贴合标准 CRUD 需求。",
    "generic-crud-factory": "泛型 CRUD 工厂，按资源名生成 router。适合多资源复用、减少样板；抽象层带来理解成本，定制单点逻辑较绕。",
    "readonly-list": "只读列表 router（仅 list/get）。适合纯展示/报表类资源；不支持写操作，需要增删改时不适用。",
    "post-router": "tRPC router，Post 资源 CRUD（t3 经典示例）。适合博客/内容类；字段固定为 Post 语义，其他资源需改写。",
    # ── 其他 ──
    "markdown-view": "Markdown 渲染组件。适合内容展示；具体依赖见 deps，注意 XSS（渲染不可信内容需 sanitize）。",
    "table-markdown-view": "支持 GFM 表格的 markdown 渲染。适合带表格的文档/笔记；inline 渲染走 dangerouslySetInnerHTML，不可信内容需 sanitize。",
    "code-block-markdown-view": "支持 ``` 代码块的 markdown 渲染，代码原样转义。适合技术博客/文档；无语法高亮（要高亮需引 highlight.js 等）。",
    "minimal-markdown-view": "极简 markdown，只渲染标题+段落、不解析 inline。最安全最轻；功能也最少，适合可信度低或只需基础排版。",
    "csv-contacts-import": "CSV 批量导入，字段固定 name/description（Contact 语义）。适合通讯录类；其他实体需改字段映射。",
    "generic-csv-import": "通用 CSV 解析，首行表头→Record<string,string>，不绑定实体。适合任意表格导入；调用方自行映射到 model。",
    "json-import": "JSON 数组批量导入，值转字符串。适合从 API/导出的 JSON 导入；非数组/非法 JSON 返回空。",
    "tsv-import": "TSV 制表符分隔导入。适合 Excel/Sheets 复制粘贴；字段含制表符会错列。",
    # ── file.upload（新 seam）──
    "data-url-upload": "base64 data URL 上传，零后端零依赖。适合 MVP/头像等小文件预览；不持久化、大文件会撑爆内存。",
    "presigned-url-upload": "PUT 到预签名 URL（S3/R2/OSS）。适合生产对象存储；需后端先签发 URL，本函数只管上传动作。",
}


def main() -> None:
    dry = "--dry-run" in sys.argv
    done = 0
    missing: list[str] = []
    for meta_path in sorted(CAND.rglob("meta.json")):
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        ml = data.get("registry_item", {}).get("meta_loom")
        if ml is None:
            continue
        ref = data.get("l0", {}).get("ref") or meta_path.parent.name
        tr = TRADEOFFS.get(ref)
        if tr is None:
            missing.append(ref)
            continue
        ml["tradeoffs"] = tr
        if not dry:
            meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  {'[dry] ' if dry else '✓ '}{ref}")
        done += 1

    print(f"\n回填 {done} 个候选{'（dry-run）' if dry else ''}。")
    if missing:
        print(f"⚠ 无 tradeoffs 文案的 ref（需补 TRADEOFFS 表）：{missing}")


if __name__ == "__main__":
    main()
