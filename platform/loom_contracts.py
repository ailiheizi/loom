"""Loom 跨语言契约 —— 单一事实源（Pydantic v2）。

这些模型是 Python 平台侧与 TS client 侧之间的硬契约。
导出 JSON Schema（见 export_schemas.py），TS 侧用 zod 镜像同形状。
MVP 阶段许多字段只占位（sha256/provenance/health），值不填，但形状定死，方便后续无缝升级。

设计原则：
- 跨语言边界只传 JSON，禁传 pickle / Python 对象。
- 内容寻址用 `sha256:<hex>`；MVP 可用文件路径占位，但字段保留。
- AssemblyPlan 是 AI 的唯一产物，output 极小（每 seam 一条决策）。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────────────
# 枚举
# ─────────────────────────────────────────────────────────────────────────────


class SeamAction(str, Enum):
    """AI 对每个 seam 的决策动作。"""

    PICK = "pick"  # 选中某候选，整文件落盘
    ADAPT = "adapt"  # 候选基本对，需额外 adapter 胶水文件
    GENERATE = "generate"  # 无合适候选，AI 自己写（兜底，WRITE_OWN）
    SKIP = "skip"  # 保留 core 自带占位


class Provenance(str, Enum):
    """候选来源，决定初始信任度。"""

    PLATFORM = "platform"  # 平台策展
    USER = "user"  # 用户上传
    SYNTHESIZED = "synthesized"  # AI 生成后回流（初始健康度低）


class BarrelOp(str, Enum):
    """接入口的 append 操作类型（文件级拼装，绝不做 AST 行级合并）。"""

    OBJECT_KEY_APPEND = "object-key-append"  # 往对象插一个 key（如 tRPC root router）
    ARRAY_APPEND = "array-append"  # 往数组插一项（如 NextAuth providers[]）
    MODEL_APPEND = "model-append"  # 往 prisma schema 追加 model
    FILE_ADD = "file-add"  # 纯新增文件，无需改入口


class FileType(str, Enum):
    """复用 shadcn registry-item 的 type 枚举，作物化 hint。"""

    LIB = "registry:lib"
    COMPONENT = "registry:component"
    HOOK = "registry:hook"
    PAGE = "registry:page"
    FILE = "registry:file"
    UI = "registry:ui"
    BLOCK = "registry:block"


# ─────────────────────────────────────────────────────────────────────────────
# Core seam 声明（loom.core.json）
# ─────────────────────────────────────────────────────────────────────────────


class BarrelSpec(BaseModel):
    """seam 的接入口规格：在哪个文件、哪个锚点、用什么 op append。"""

    file: str = Field(description="core 内的接入口文件，如 src/server/api/root.ts")
    anchor_import: str | None = Field(
        default=None, description="import 区锚点注释，如 // <loom-anchor:router-imports>"
    )
    anchor_register: str | None = Field(
        default=None, description="注册区锚点注释，如 // <loom-anchor:router-register>"
    )
    op: BarrelOp = Field(description="append 操作类型")


class SeamSpec(BaseModel):
    """core 暴露的一个接缝（扩展点）。"""

    seam_id: str = Field(description="唯一接缝 id，如 auth.oauth_provider")
    kind: str = Field(description="接缝种类，如 nextauth-provider / trpc-router / route-handler / ui-component")
    signature: str = Field(description="接口签名（自然语言或类型字符串）")
    signature_ref: str | None = Field(
        default=None, description="指向真实 .d.ts 类型的引用，强制机器可读时填（命门#4）"
    )
    barrel: BarrelSpec = Field(description="接入口规格")
    target: str = Field(description="pick 候选文件落盘的目标目录")
    compat_range: str | None = Field(default=None, description="兼容版本范围，如 next-auth@^5")
    cardinality: str = Field(default="one", description="one | many；many 表一个 seam 可装多个候选")
    env_vars: list[str] = Field(default_factory=list, description="该 seam 连带需要的环境变量名")


class CoreManifest(BaseModel):
    """loom.core.json —— 一个 core 的 seam 声明清单。"""

    core_id: str = Field(description="core 标识，如 create-t3-app")
    core_version: str = Field(description="钉死的版本")
    content_hash: str | None = Field(default=None, description="sha256:<hex>，MVP 可空")
    language: str = Field(default="typescript")
    seams: list[SeamSpec] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# 候选 registry item（复用 shadcn 契约 + meta.loom 扩展）
# ─────────────────────────────────────────────────────────────────────────────


class RegistryFile(BaseModel):
    """候选包含的一个文件。"""

    path: str = Field(description="候选内相对路径")
    type: FileType = Field(default=FileType.LIB)
    target: str = Field(description="物化到 core 的目标路径（Loom 强制必填，确定性物化）")
    hash: str | None = Field(default=None, description="sha256:<hex>，MVP 可空")


class ExtPkg(BaseModel):
    """候选依赖的外部 npm 包。"""

    name: str
    version: str = Field(description="精确 pin 版本")
    license: str | None = None


class LoomMeta(BaseModel):
    """塞进 shadcn meta.loom 的 Loom 私货，对 shadcn 工具链无害。"""

    seam_id: str = Field(description="该候选实现的 seam")
    interface_sig: str = Field(description="导出符号的接口签名")
    provenance: Provenance = Field(default=Provenance.PLATFORM)
    health: float = Field(default=1.0, ge=0.0, le=1.0, description="0-1，synthesized 初始低")
    content_hash: str | None = Field(default=None)
    license: str | None = None
    ext_pkgs: list[ExtPkg] = Field(default_factory=list)


class RegistryItem(BaseModel):
    """候选文件/组件，复用 shadcn registry-item.json 字段。"""

    name: str
    type: FileType = Field(default=FileType.LIB)
    title: str | None = None
    description: str | None = None
    dependencies: list[str] = Field(default_factory=list, description="npm 包，pinned")
    registry_dependencies: list[str] = Field(default_factory=list, description="依赖的其他 registry item")
    files: list[RegistryFile] = Field(default_factory=list)
    css_vars: dict = Field(default_factory=dict)
    env_vars: dict[str, str] = Field(default_factory=dict)
    meta_loom: LoomMeta = Field(description="Loom 装配元数据")


# ─────────────────────────────────────────────────────────────────────────────
# 披露式展开各层（L0/L1/L2）
# ─────────────────────────────────────────────────────────────────────────────


class L0Candidate(BaseModel):
    """L0 候选清单项（粗筛，input 极省）。"""

    ref: str = Field(description="候选标识")
    seam_id: str
    summary: str = Field(description="一句话能力意图摘要（召回命门）")
    deps: list[str] = Field(default_factory=list)
    loc: int = Field(default=0)
    health: float = Field(default=1.0)
    provenance: Provenance = Field(default=Provenance.PLATFORM)
    content_hash: str | None = Field(default=None)


class L1Export(BaseModel):
    """L1 导出符号签名（不含函数体）。"""

    name: str
    signature: str
    kind: str = Field(default="function", description="function | class | const | type")


class L1Signature(BaseModel):
    """L1 接口签名层（多数 case AI 看这层即可定）。"""

    ref: str
    content_hash: str | None = Field(default=None)
    exports: list[L1Export] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list, description="相关类型定义字符串")
    imports: list[str] = Field(default_factory=list)


class L2File(BaseModel):
    """L2 全文层的一个文件。"""

    path: str
    content: str
    hash: str | None = Field(default=None)


class L2FullText(BaseModel):
    """L2 全文（AI 明确 EXPAND 才给，最贵）。"""

    ref: str
    content_hash: str | None = Field(default=None)
    files: list[L2File] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# AssemblyPlan（AI 的唯一产物，output 极小）
# ─────────────────────────────────────────────────────────────────────────────


class SelectionDecision(BaseModel):
    """对一个 seam 的选择决策。"""

    seam_id: str
    action: SeamAction
    ref: str | None = Field(default=None, description="pick/adapt 时选中的候选")
    content_hash: str | None = Field(default=None)
    adapter: str | None = Field(default=None, description="adapt 时需要的胶水说明（一句话）")
    generated_file: str | None = Field(
        default=None, description="generate 时 AI 真写的文件路径（走单独通道）"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="AI 自评")
    why: str = Field(default="", description="一句话理由，可截断")


class TokenBudget(BaseModel):
    """client 回填用于 h* 埋点。"""

    input_tok: int = 0
    output_tok: int = 0


class AssemblyPlan(BaseModel):
    """AI 输出的装配清单。"""

    idea_id: str
    core_ref: str = Field(description="如 create-t3-app@7.39.x")
    seams: list[SelectionDecision] = Field(default_factory=list)
    synthesized: list[str] = Field(
        default_factory=list, description="generate 产物文件列表，过 Gate-1 后回流飞轮"
    )
    budget: TokenBudget = Field(default_factory=TokenBudget)


# ─────────────────────────────────────────────────────────────────────────────
# 候选梯度提案（第二步：候选级梯度呈现）
# server 对每个 seam 召回 2-3 个真实候选 + 架构取舍，供宿主 agent 摊给架构师挑。
# 纯检索产物，零 LLM。这是 agent-native 愿景里 server 的核心只读能力之一。
# ─────────────────────────────────────────────────────────────────────────────


class CandidateProposal(BaseModel):
    """单个候选的提案视图（给架构师做决策的最小信息集）。"""

    ref: str = Field(description="候选标识")
    summary: str = Field(description="一句话能力摘要")
    deps: list[str] = Field(default_factory=list, description="外部 npm 依赖；空=零依赖")
    health: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Provenance = Field(default=Provenance.PLATFORM)
    score: float = Field(default=0.0, description="检索综合分（越高越贴合需求）")
    tradeoffs: str = Field(
        default="", description="架构取舍说明：依赖/复杂度/适用场景，供架构师判断"
    )
    recommended: bool = Field(default=False, description="检索排序第一=默认推荐项")


class SeamProposal(BaseModel):
    """一个 seam 的候选梯度（2-3 个真实候选；空=该 seam 无候选需 generate）。"""

    seam_id: str
    intent: str = Field(description="该 seam 对应的能力意图（来自想法）")
    candidates: list[CandidateProposal] = Field(default_factory=list)
    needs_generate: bool = Field(
        default=False, description="True=池内无候选，只能从零生成"
    )


class GradientProposal(BaseModel):
    """一个想法的完整候选梯度提案。宿主 agent 读它，逐 seam 摊给用户挑。"""

    idea_id: str
    core_ref: str = Field(description="如 create-t3-app@7.39.x")
    seams: list[SeamProposal] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# 物化两件套：manifest + lockfile（client 拿到后确定性物化）
# ─────────────────────────────────────────────────────────────────────────────


class ManifestFile(BaseModel):
    """manifest 中声明的一个目标文件来源。"""

    target: str = Field(description="目标项目内的文件路径")
    source: str = Field(description="来源：sha256:<hex> 或 MVP 下的候选文件路径")
    op: BarrelOp = Field(default=BarrelOp.FILE_ADD)


class BarrelMutation(BaseModel):
    """对接入口文件的一次 append 操作。"""

    file: str
    anchor: str = Field(description="目标锚点注释")
    op: BarrelOp
    snippet: str = Field(description="要 append 的代码片段")


class Manifest(BaseModel):
    """平台 resolve 出的确定性物化清单。"""

    core_ref: str
    files: list[ManifestFile] = Field(default_factory=list)
    barrel_ops: list[BarrelMutation] = Field(default_factory=list)
    deps: list[ExtPkg] = Field(default_factory=list)
    env_vars: list[str] = Field(default_factory=list)


class Lockfile(BaseModel):
    """target → source@hash 全量映射 + 整树 merkle root，供校验与回滚。"""

    root: str | None = Field(default=None, description="整树 merkle root，sha256:<hex>，MVP 可空")
    entries: dict[str, str] = Field(
        default_factory=dict, description="target 路径 → source@hash"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 闸门诊断 + 指标埋点
# ─────────────────────────────────────────────────────────────────────────────


class Diagnostic(BaseModel):
    """ts-morph getPreEmitDiagnostics 输出的一条结构化诊断。"""

    file: str
    line: int
    column: int
    code: int = Field(description="TS 错误码，如 2307")
    message: str
    category: str = Field(default="error", description="error | warning")


class RepairRound(BaseModel):
    """修复循环的一轮记录。"""

    round_index: int
    error_count: int
    error_fingerprints: list[str] = Field(
        default_factory=list, description="用于震荡检测（错误指纹集是否严格下降）"
    )
    input_tok: int = 0
    output_tok: int = 0
    auto_fixed: int = Field(default=0, description="确定性机器自动修掉的数量")


class AssemblyMetrics(BaseModel):
    """一次组装的完整埋点（组装臂/从零臂共用）。"""

    arm: str = Field(description="assembly | from_zero | oracle")
    idea_id: str
    total_input_tok: int = 0
    total_output_tok: int = 0
    retry_input_tok: int = Field(
        default=0, description="instructor schema 重试消耗，单独计量不计入 ΔRepair"
    )
    disclosure_input_tok: int = Field(
        default=0, description="选择期 input（h* 的披露input项）；from_zero 臂=0"
    )
    disclosure_output_tok: int = Field(
        default=0, description="选择期 output（小）；from_zero 臂=0"
    )
    rounds: list[RepairRound] = Field(default_factory=list)
    converged: bool = Field(default=False, description="3 轮内是否到 0 error")
    final_error_count: int = 0
    write_own_ratio: float = Field(default=0.0, description="action=generate 的 seam 占比")
    fix_diff_lines: int | None = Field(default=None, description="到 0-error 后人工 fix 行数")
    extend_diff_lines: int | None = Field(default=None, description="extend 行数，不计扣分")
    total_delivered_lines: int | None = Field(default=None)

    @property
    def equiv_cost(self) -> float:
        """等效成本 = output + input/4（r=4）。"""
        return self.total_output_tok + self.total_input_tok / 4

    @property
    def delta_repair_input(self) -> int:
        """ΔRepair：第 0 轮之后修复循环累积的 input token。"""
        if len(self.rounds) <= 1:
            return 0
        return sum(r.input_tok for r in self.rounds[1:])


class HStarReport(BaseModel):
    """h* 归因报告：组装臂相对从零臂的等效成本比。

    h* = (disclosure_input + delta_repair_input + amortized) / (G * r)
    其中 G = from_zero.total_output_tok（从零臂的生成产出，即组装臂省下的）。
    h* < 1 表示组装更省，但见 docs/T8-doubt-register.md B1：所有 mock 单向压低 h*，
    故 h*<1 不能证真实系统省 token，只有 h*>1 是稳健 Kill。
    """

    idea_id: str
    r: float = Field(default=4.0, description="input/output 等效折算比（硬编码，见 B5）")
    G: int | None = Field(default=None, description="从零臂 total_output_tok；缺则 h* pending")
    disclosure_input: int | None = None
    delta_repair_input: int | None = None
    amortized: float | None = Field(default=None, description="None=M4 排除摊销，不计为 0")
    h_star: float | None = Field(default=None, description="缺 from_zero 基准则为 None")
    status: str = Field(default="pending(需from_zero基准)")
    equiv_cost_assembly: float | None = None
    equiv_cost_from_zero: float | None = None
    sources: dict[str, str] = Field(default_factory=dict)


def compute_h_star(
    assembly: AssemblyMetrics,
    from_zero: AssemblyMetrics | None,
    r: float = 4.0,
    amortized: float | None = None,
) -> HStarReport:
    """算 h*。缺 from_zero 基准则标 pending、不填 0（决策 2 / 审计 B2）。"""
    sources = {
        "disclosure_input": "assembly.disclosure_input_tok（选择期，plan.budget）",
        "delta_repair_input": "assembly.delta_repair_input（rounds[1:].input）",
        "G": "from_zero.total_output_tok",
        "amortized": "EXCLUDED — M4 摊销不计（非测量为0）"
        if amortized is None
        else "provided",
        "r": "硬编码 r=4（B5：网关缓存分层未证）",
    }
    base = HStarReport(
        idea_id=assembly.idea_id,
        r=r,
        disclosure_input=assembly.disclosure_input_tok,
        delta_repair_input=assembly.delta_repair_input,
        amortized=amortized,
        equiv_cost_assembly=assembly.equiv_cost,
        sources=sources,
    )
    # 缺基准 → pending，不算 h*
    if from_zero is None or from_zero.total_output_tok <= 0:
        return base
    G = from_zero.total_output_tok
    numerator = assembly.disclosure_input_tok + assembly.delta_repair_input + (amortized or 0.0)
    base.G = G
    base.h_star = numerator / (G * r)
    base.status = "ok"
    base.equiv_cost_from_zero = from_zero.equiv_cost
    return base
