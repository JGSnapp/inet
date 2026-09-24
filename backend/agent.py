from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from models import create_chat_model
from tools import TOOLS


SYSTEM_PROMPT = """
Ты универсальный чат-бот агент. Отвечай понятно и кратко на языке пользователя.
Если вопрос касается данных в базе, обязательно используй инструменты поиска
и получения документов. Не выдумывай содержимое документов и указывай их ID.
Для обычной беседы инструменты использовать не обязательно.
""".strip()


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content)


@lru_cache(maxsize=1)
def get_agent():
    model_with_tools = create_chat_model().bind_tools(TOOLS)

    async def call_model(state: MessagesState) -> dict[str, list[AIMessage]]:
        response = await model_with_tools.ainvoke(
            [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        )
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode(TOOLS, handle_tool_errors=True))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition, ["tools", END])
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=InMemorySaver())


async def run_agent(message: str, thread_id: str) -> str:
    result = await get_agent().ainvoke(
        {"messages": [{"role": "user", "content": message}]},
        {"configurable": {"thread_id": thread_id}, "recursion_limit": 12},
    )
    return _content_to_text(result["messages"][-1].content)
