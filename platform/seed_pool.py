"""验池实验灌密脚本（一次性）—— 把 .work/pool-density-src/ 下的真实 TS 源批量 ingest 入池。

目的（见 docs/agent-native-vision-assessment.md + plan compiled-singing-wave）：
把 SaaS 后台 2 个高频 seam 灌密——ui.data_table 2→8、report.custom_export 1→6，
验证"池密度→pick 可选度上升、组装净赢生成"。

零 LLM：纯复用 ingest.ingest_file（tree-sitter 抽签名 + 模板生成 meta.json）。
幂等：重复跑覆盖同名候选目录。

用法：cd platform && uv run python seed_pool.py [--dry-run]
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ingest import ingest_file

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / ".work" / "pool-density-src"
CANDIDATES = ROOT / "candidates"

# 灌密清单：每条 = (源文件相对 SRC 路径, seam_id, ref, summary, target)
# target 与各 seam 现有候选保持一致（同 seam 候选落同一目标路径，才能被同一想法 pick）。
SEED: list[tuple[str, str, str, str, str]] = [
    # ── ui.data_table（落 src/app/_components/data-table.tsx）──
    ("ui.data_table/paginated-data-table.tsx", "ui.data_table", "paginated-data-table",
     "客户端分页数据表格，可选 pageSize，底部上一页/下一页控件。零依赖。", "src/app/_components/data-table.tsx"),
    ("ui.data_table/sortable-data-table.tsx", "ui.data_table", "sortable-data-table",
     "可排序数据表格，点击表头在 asc/desc/无序间循环，零依赖（不引 tanstack）。", "src/app/_components/data-table.tsx"),
    ("ui.data_table/filterable-data-table.tsx", "ui.data_table", "filterable-data-table",
     "带全局文本筛选的数据表格，顶部搜索框跨列大小写不敏感匹配。零依赖。", "src/app/_components/data-table.tsx"),
    ("ui.data_table/compact-data-table.tsx", "ui.data_table", "compact-data-table",
     "紧凑只读数据表格，小行距密集展示，适合 dashboard 卡片内。纯展示无 state。", "src/app/_components/data-table.tsx"),
    ("ui.data_table/selectable-data-table.tsx", "ui.data_table", "selectable-data-table",
     "可多选行的数据表格，左侧复选框列，支持全选/单选 + 已选计数。零依赖。", "src/app/_components/data-table.tsx"),
    ("ui.data_table/striped-numeric-data-table.tsx", "ui.data_table", "striped-numeric-data-table",
     "斑马纹数据表格，数字列自动右对齐，适合财务/报表只读展示。零依赖。", "src/app/_components/data-table.tsx"),
    # ── report.custom_export（落 src/server/export/）──
    ("report.custom_export/json-export.ts", "report.custom_export", "json-export-fn",
     "rowsToJson/toJsonBlob 把行数据导出为 pretty JSON，支持列投影。零依赖。", "src/server/export/json-export.ts"),
    ("report.custom_export/tsv-export.ts", "report.custom_export", "tsv-export-fn",
     "rowsToTsv/toTsvBlob 制表符分隔导出，Excel/Sheets 粘贴友好。零依赖。", "src/server/export/tsv-export.ts"),
    ("report.custom_export/clipboard-export.ts", "report.custom_export", "clipboard-export-fn",
     "rowsToClipboardText/copyToClipboard 复制 CSV 到剪贴板，浏览器原生 clipboard API。零依赖。", "src/server/export/clipboard-export.ts"),
    ("report.custom_export/markdown-export.ts", "report.custom_export", "markdown-export-fn",
     "rowsToMarkdown/toMarkdownBlob 导出 GFM 表格，适合贴进 README/issue/文档。零依赖。", "src/server/export/markdown-export.ts"),
    ("report.custom_export/excel-csv-export.ts", "report.custom_export", "excel-csv-export-fn",
     "rowsToExcelCsv/toExcelCsvBlob 带 UTF-8 BOM 的 CSV，解决 Excel 中文乱码。零依赖。", "src/server/export/excel-csv-export.ts"),
    # ── content.markdown_render（落 src/app/_components/markdown-view.tsx）规模化扩池 ──
    ("content.markdown_render/table-markdown-view.tsx", "content.markdown_render", "table-markdown-view",
     "支持 GFM 表格的 markdown 渲染，解析 | a | b | 表格。零依赖正则。", "src/app/_components/markdown-view.tsx"),
    ("content.markdown_render/code-block-markdown-view.tsx", "content.markdown_render", "code-block-markdown-view",
     "支持 ``` 代码块的 markdown 渲染，代码块内原样转义。零依赖。", "src/app/_components/markdown-view.tsx"),
    ("content.markdown_render/minimal-markdown-view.tsx", "content.markdown_render", "minimal-markdown-view",
     "极简 markdown 渲染，只处理标题与段落，不解析 inline，最安全最轻。零依赖。", "src/app/_components/markdown-view.tsx"),
    # ── data.bulk_import（落 src/server/import/）规模化扩池 ──
    ("data.bulk_import/generic-csv-import.ts", "data.bulk_import", "generic-csv-import",
     "parseCsv 通用 CSV 解析，首行表头映射为 Record，不绑定具体实体。零依赖。", "src/server/import/csv-import.ts"),
    ("data.bulk_import/json-import.ts", "data.bulk_import", "json-import",
     "parseJsonImport 解析 JSON 数组批量导入，值转字符串。零依赖。", "src/server/import/json-import.ts"),
    ("data.bulk_import/tsv-import.ts", "data.bulk_import", "tsv-import",
     "parseTsvImport 制表符分隔导入，适合 Excel/Sheets 粘贴。零依赖。", "src/server/import/tsv-import.ts"),
    # ── file.upload（新 seam，落 src/lib/upload/）规模化加新 seam ──
    ("file.upload/data-url-upload.ts", "file.upload", "data-url-upload",
     "uploadFile 把 File 读成 base64 data URL，零后端零依赖，适合 MVP/小文件预览。", "src/lib/upload/data-url-upload.ts"),
    ("file.upload/presigned-url-upload.ts", "file.upload", "presigned-url-upload",
     "uploadFile 把文件 PUT 到预签名 URL（S3/R2/OSS 模式），浏览器原生 fetch，零依赖。", "src/lib/upload/presigned-url-upload.ts"),
    # ── ui.form（新 seam，落 src/app/_components/form-view.tsx）让 CRUD 闭环 ──
    ("ui.form/simple-form.tsx", "ui.form", "simple-form",
     "基础受控表单，每字段一个 text input，提交回调 Record。零依赖，配 CRUD create/update。", "src/app/_components/form-view.tsx"),
    ("ui.form/validated-form.tsx", "ui.form", "validated-form",
     "带必填校验的受控表单，required 字段为空阻止提交并显错。零依赖。", "src/app/_components/form-view.tsx"),
    ("ui.form/typed-form.tsx", "ui.form", "typed-form",
     "多字段类型表单（text/textarea/select）。零依赖，适合字段多样的实体编辑。", "src/app/_components/form-view.tsx"),
    # ── ui.layout（新 seam，落 src/app/_components/app-layout.tsx）应用骨架 ──
    ("ui.layout/sidebar-layout.tsx", "ui.layout", "sidebar-layout",
     "侧边栏应用布局，左侧固定导航+右侧内容区。零依赖，适合后台管理骨架。", "src/app/_components/app-layout.tsx"),
    ("ui.layout/topbar-layout.tsx", "ui.layout", "topbar-layout",
     "顶栏应用布局，顶部水平导航+居中内容区。零依赖，适合内容站/简单应用。", "src/app/_components/app-layout.tsx"),
    # ── ui.detail（新 seam，落 src/app/_components/detail-view.tsx）详情展示 ──
    ("ui.detail/field-list-detail.tsx", "ui.detail", "field-list-detail",
     "字段列表式详情（dl/dt/dd 定义列表）。零依赖，fields 省略则展示所有键。", "src/app/_components/detail-view.tsx"),
    ("ui.detail/card-detail.tsx", "ui.detail", "card-detail",
     "卡片式详情，带标题的网格卡片展示字段。零依赖，适合单条资源展示。", "src/app/_components/detail-view.tsx"),
    # ── auth.oauth_provider 扩展：magic-link 邮箱登录 ──
    ("auth.oauth_provider/magic-link.ts", "auth.oauth_provider", "magic-link",
     "Magic-link 风格邮箱登录（Credentials 实现，零依赖）。邮箱+验证码登录，加入 providers[]。", "src/server/auth/providers/magic-link.ts"),
]


def main() -> None:
    dry = "--dry-run" in sys.argv
    print(f"=== 验池灌密 {'(dry-run)' if dry else ''} ===")
    print(f"源目录: {SRC}")
    if not SRC.exists():
        print(f"✗ 源目录不存在: {SRC}")
        sys.exit(1)

    done = 0
    for rel, seam_id, ref, summary, target in SEED:
        src_path = SRC / rel
        if not src_path.exists():
            print(f"  ✗ 缺源文件: {rel}")
            continue
        if dry:
            print(f"  [dry] {seam_id}/{ref}  ← {rel}")
            done += 1
            continue
        meta_path = ingest_file(
            src_path=src_path,
            seam_id=seam_id,
            ref=ref,
            summary=summary,
            target=target,
            candidates_root=CANDIDATES,
        )
        print(f"  ✓ {seam_id}/{ref}  → {meta_path.relative_to(ROOT)}")
        done += 1

    print(f"\n灌密 {done}/{len(SEED)} 个候选{'（dry-run，未写盘）' if dry else ''}。")
    if not dry:
        print("下一步：uv run python verify_candidates.py 过质量门 → eval 看离线指标变化。")


if __name__ == "__main__":
    main()
