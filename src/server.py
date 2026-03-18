import asyncio
import base64
import os
import time

import httpx
import mcp.types as types
import uvicorn
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route

# ==========================================
# 1. 基础配置与环境变量
# ==========================================
load_dotenv()
OPENCODE_URL = os.getenv("OPENCODE_URL", "http://127.0.0.1:4096").rstrip("/")
OPENCODE_PASSWORD = os.getenv("OPENCODE_SERVER_PASSWORD")
MCP_PORT = int(os.getenv("MCP_PORT", 14962))
# ✅ 可配置的超时时间，默认 60 秒
TASK_TIMEOUT = int(os.getenv("OPENCODE_TASK_TIMEOUT", 60))


def get_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if OPENCODE_PASSWORD:
        auth_str = f"opencode:{OPENCODE_PASSWORD}"
        headers["Authorization"] = f"Basic {base64.b64encode(auth_str.encode()).decode()}"
    return headers


# ==========================================
# 2. 初始化底层 Server & 注册 4 个核心工具
# ==========================================
app_server = Server("opencode-modular-agent")


@app_server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="opencode_create_session",
            description=(
                "【第 1 步：创建会话】在 OpenCode 中创建一个全新的空白会话 (Session)。\n"
                "使用场景：当用户需要执行一个全新任务，且没有指定历史会话时，必须首先调用此工具。\n"
                "返回值：返回一个以 'ses_' 开头的会话 ID。拿到 ID 后，请继续使用 `opencode_send_prompt` 发送指令。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "(可选) 给这个会话起个简短的标题，方便日后查找。",
                    }
                },
            },
        ),
        types.Tool(
            name="opencode_send_prompt",
            description=(
                f"【第 2 步：发送指令】向指定的 OpenCode 会话发送自然语言指令或代码任务。\n"
                f"使用场景：你已经有了一个 Session ID（通过创建或查询列表获得），现在要把任务发给它执行。\n"
                f"行为逻辑：\n"
                f"1. 发送后，系统最多会等待 {TASK_TIMEOUT} 秒。\n"
                f"2. 如果任务在此时间内完成，将直接返回最终代码或执行结果。\n"
                f"3. 如果任务超时未完成，将返回『后台执行中』的提示。\n"
                f"重要约束：如果收到『后台执行中』的提示，你必须主动调用 `opencode_check_session` 去轮询执行结果，绝不能直接编造代码给用户。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "目标会话 ID，例如 ses_xxxx"},
                    "prompt": {"type": "string", "description": "要执行的具体指令或要发送的代码。"},
                },
                "required": ["session_id", "prompt"],
            },
        ),
        types.Tool(
            name="opencode_check_session",
            description=(
                "【第 3 步：查看会话完整内容与进度】获取指定会话的当前运行状态，以及从创建至今的『完整历史对话记录』。\n"
                "使用场景：\n"
                "1. 发送指令后，查询任务是否执行完成。\n"
                "2. 刚接手一个历史 Session ID 时，调用此工具读取之前的全部上下文，了解前因后果。\n"
                "行为逻辑：返回内容包含当前 Status 以及完整的消息列表。请仔细阅读历史记录中的报错或输出，再决定下一步操作。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "要查询的会话 ID。"}
                },
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="opencode_list_sessions",
            description=(
                "【辅助工具：获取会话列表】获取当前系统的历史会话记录。\n"
                "使用场景：当用户想继续之前的工作，但没有提供 Session ID 时，调用此工具获取列表，根据标题(title)匹配到正确的 ID，然后再进行后续操作。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "返回的会话数量，默认获取最近的 10 个。",
                    }
                },
            },
        ),
    ]


@app_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    headers = get_headers()

    async with httpx.AsyncClient() as client:
        try:
            # ---------------------------------------------------------
            # 工具 1：创建 Session
            # ---------------------------------------------------------
            if name == "opencode_create_session":
                title = arguments.get("title", "New Task")
                payload = {"title": title}

                create_res = await client.post(
                    f"{OPENCODE_URL}/session", headers=headers, json=payload, timeout=10.0
                )
                create_res.raise_for_status()

                res_json = create_res.json()
                session_id = res_json.get("data")
                if isinstance(session_id, dict):
                    session_id = session_id.get("sessionID", session_id.get("id"))

                if not session_id:
                    return [
                        types.TextContent(type="text", text=f"❌ 创建 Session 失败: {res_json}")
                    ]

                return [
                    types.TextContent(
                        type="text",
                        text=f"✅ 会话创建成功！\nSession ID: `{session_id}`\n请立即使用 `opencode_send_prompt` 工具向此会话发送任务指令。",
                    )
                ]

            # ---------------------------------------------------------
            # 工具 2：发送 Prompt 并智能等待 (带超时机制)
            # ---------------------------------------------------------
            elif name == "opencode_send_prompt":
                session_id = arguments.get("session_id")
                prompt = arguments.get("prompt")

                payload = {"parts": [{"type": "text", "text": prompt}]}

                # 1. 触发任务执行 (短超时，不阻塞)
                try:
                    await client.post(
                        f"{OPENCODE_URL}/session/{session_id}/message",
                        headers=headers,
                        json=payload,
                        timeout=2.0,
                    )
                except httpx.ReadTimeout:
                    pass

                # 2. 轮询等待，受 TASK_TIMEOUT 环境变量控制
                start_time = time.time()
                while time.time() - start_time < TASK_TIMEOUT:
                    await asyncio.sleep(3.0)  # 每 3 秒检查一次

                    try:
                        msg_res = await client.get(
                            f"{OPENCODE_URL}/session/{session_id}/message",
                            headers=headers,
                            timeout=5.0,
                        )
                        if msg_res.status_code == 200:
                            raw_data = msg_res.json()
                            messages = (
                                raw_data.get("data", raw_data)
                                if isinstance(raw_data, dict)
                                else raw_data
                            )

                            if messages and isinstance(messages, list):
                                last_msg = messages[-1]
                                is_assistant = (
                                    last_msg.get("role") == "assistant" or "parts" in last_msg
                                )
                                status = last_msg.get("status", last_msg.get("state", "未知"))
                                is_running = status in ["running", "in_progress"]

                                # 任务已完成，直接返回最后一条内容
                                if is_assistant and not is_running:
                                    content = ""
                                    if "parts" in last_msg:
                                        content = "\n".join(
                                            [
                                                p.get("text", "")
                                                for p in last_msg.get("parts", [])
                                                if p.get("type") == "text"
                                            ]
                                        )
                                    else:
                                        content = last_msg.get("content", str(last_msg))

                                    return [
                                        types.TextContent(
                                            type="text",
                                            text=f"✅ 任务执行完成！(耗时 {int(time.time() - start_time)}s)\n\n【最新执行结果】:\n{content}",
                                        )
                                    ]
                    except Exception:
                        pass  # 忽略轮询中偶发的网络抖动

                # 3. 如果循环结束仍未完成，返回后台执行提示
                return [
                    types.TextContent(
                        type="text",
                        text=f"⏳ 任务比较复杂，已超过预设的 {TASK_TIMEOUT} 秒，仍在后台努力执行中。\n\n【Session ID】: `{session_id}`\n请稍后使用 `opencode_check_session` 工具查询最终结果。",
                    )
                ]

            # ---------------------------------------------------------
            # 工具 3：查看 Session 完整内容与进度
            # ---------------------------------------------------------
            elif name == "opencode_check_session":
                session_id = arguments.get("session_id")
                msg_res = await client.get(
                    f"{OPENCODE_URL}/session/{session_id}/message", headers=headers, timeout=10.0
                )
                msg_res.raise_for_status()

                raw_data = msg_res.json()
                messages = (
                    raw_data.get("data", raw_data) if isinstance(raw_data, dict) else raw_data
                )

                if not messages or not isinstance(messages, list):
                    return [
                        types.TextContent(
                            type="text", text=f"会话 `{session_id}` 当前为空，或找不到该会话。"
                        )
                    ]

                # 1. 解析完整历史记录
                history_text = ""
                for idx, msg in enumerate(messages):
                    role = msg.get("role", "unknown").upper()

                    content = ""
                    if "parts" in msg:
                        content = "".join(
                            [
                                p.get("text", "")
                                for p in msg.get("parts", [])
                                if p.get("type") == "text"
                            ]
                        )
                    else:
                        content = msg.get("content", "")

                    history_text += f"[{role}] (消息 {idx + 1}):\n{content}\n"
                    history_text += "-" * 40 + "\n"

                # 2. 提取最新状态
                last_msg = messages[-1]
                status = last_msg.get("status", last_msg.get("state", "unknown"))
                is_running = status in ["running", "in_progress"]

                # 3. 组装最终返回文本
                header = f"【Session ID】: {session_id}\n"
                if is_running:
                    header += f"【当前状态】: 🔄 仍在运行中... (status: {status})\n"
                    header += (
                        "提示：底层 Agent 还在输出或执行中，以下为截止到目前的日志/对话内容。\n"
                    )
                else:
                    header += f"【当前状态】: ✅ 已完成/空闲 (status: {status})\n"

                final_response = (
                    f"{header}\n================ 完整会话记录 ================\n{history_text}"
                )

                return [types.TextContent(type="text", text=final_response)]

            # ---------------------------------------------------------
            # 工具 4：获取 Session 列表
            # ---------------------------------------------------------
            elif name == "opencode_list_sessions":
                limit = arguments.get("limit", 10)
                try:
                    list_res = await client.get(
                        f"{OPENCODE_URL}/session", headers=headers, timeout=10.0
                    )
                    list_res.raise_for_status()

                    raw_data = list_res.json()
                    sessions = (
                        raw_data.get("data", raw_data) if isinstance(raw_data, dict) else raw_data
                    )

                    if not sessions or not isinstance(sessions, list):
                        return [types.TextContent(type="text", text="当前没有找到任何历史会话。")]

                    sessions = sessions[:limit]

                    result_text = "【最近的历史会话列表】:\n"
                    for s in sessions:
                        sid = s.get("id", s.get("sessionID", "未知 ID"))
                        title = s.get("title", s.get("topic", s.get("name", "无标题")))
                        status = s.get("status", s.get("state", "未知状态"))
                        result_text += f"- ID: `{sid}` | 状态: {status} | 标题: {title}\n"

                    return [types.TextContent(type="text", text=result_text)]

                except httpx.HTTPStatusError as e:
                    return [
                        types.TextContent(
                            type="text",
                            text=f"❌ 获取列表失败，HTTP 错误码: {e.response.status_code}",
                        )
                    ]

            else:
                raise ValueError(f"未知的工具调用: {name}")

        except Exception as e:
            return [types.TextContent(type="text", text=f"❌ MCP 发生内部错误: {str(e)}")]


# ==========================================
# 3. 搭建 SSE 传输层 (纯正 ASGI)
# ==========================================
sse = SseServerTransport("/messages")


class SSEEndpoint:
    async def __call__(self, scope, receive, send):
        async with sse.connect_sse(scope, receive, send) as (read_stream, write_stream):
            await app_server.run(
                read_stream, write_stream, app_server.create_initialization_options()
            )


class MessagesEndpoint:
    async def __call__(self, scope, receive, send):
        await sse.handle_post_message(scope, receive, send)


starlette_app = Starlette(
    routes=[
        Route("/sse", endpoint=SSEEndpoint()),
        Route("/messages", endpoint=MessagesEndpoint(), methods=["POST"]),
    ]
)


# ==========================================
# 4. 启动服务
# ==========================================
def run():
    print("=========================================")
    print("🚀 OpenCode MCP Server 已启动")
    print(f"🎯 目标节点: {OPENCODE_URL}")
    print(f"⏱️ 任务超时时间: {TASK_TIMEOUT} 秒")
    print(f"🔗 SSE URL:  http://127.0.0.1:{MCP_PORT}/sse")
    print("=========================================")

    uvicorn.run(starlette_app, host="0.0.0.0", port=MCP_PORT)


if __name__ == "__main__":
    run()
