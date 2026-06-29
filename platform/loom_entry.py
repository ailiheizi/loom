"""Loom MCP 入口 —— uvx / PyInstaller 共用。

uvx 用法（发布到 PyPI 后）:
  .mcp.json: {"mcpServers": {"loom": {"command": "uvx", "args": ["loom-mcp"]}}}
PyInstaller 用法: 直接跑打包后的 loom-mcp 可执行文件
两种都调 main()。
"""
import sys
import os


def main():
    """MCP server 入口。stdio（默认）或 --http。"""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
        sys.path.insert(0, base)
        os.environ.setdefault("LOOM_STORE_DIR", os.path.join(os.path.expanduser("~"), ".loom"))

    from mcp_server import mcp
    try:
        from propose import warmup
        warmup()
    except Exception:
        pass

    if "--http" in sys.argv:
        os.environ["LOOM_TRANSPORT"] = "http"
        mcp.settings.host = os.environ.get("LOOM_HOST", "127.0.0.1")
        mcp.settings.port = int(os.environ.get("LOOM_PORT", "8000"))
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
