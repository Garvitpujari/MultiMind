from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langchain_groq import ChatGroq
from contextlib import asynccontextmanager
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool, BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from dotenv import load_dotenv

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

import requests
import asyncio
import threading
import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is missing.")

    async with AsyncPostgresSaver.from_conn_string(
        database_url
    ) as checkpointer:
        await checkpointer.setup()

        app.state.checkpointer = checkpointer
        app.state.chatbot = graph.compile(
            checkpointer=checkpointer
        )

        yield


app = FastAPI(
    title="MultiMind API",
    lifespan=lifespan
)



frontend_url = os.getenv(
    "FRONTEND_URL",
    "http://localhost:8501"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        frontend_url,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app": "MultiMind API"
    }

class ChatRequest(BaseModel):
    message: str
    thread_id: str

# Dedicated async loop for backend tasks
_ASYNC_LOOP = asyncio.new_event_loop()
_ASYNC_THREAD = threading.Thread(target=_ASYNC_LOOP.run_forever, daemon=True)
_ASYNC_THREAD.start()


def _submit_async(coro):
    return asyncio.run_coroutine_threadsafe(coro, _ASYNC_LOOP)


def run_async(coro):
    return _submit_async(coro).result()


def submit_async_task(coro):
    """Schedule a coroutine on the backend event loop."""
    return _submit_async(coro)


# -------------------
# 1. LLM
# -------------------
llm = ChatGroq(model='openai/gpt-oss-120b')

# -------------------
# 2. Tools
# -------------------
search_tool = DuckDuckGoSearchRun(region="us-en")


@tool
def get_stock_price(symbol: str) -> dict:
    """Fetch the latest stock quote using Alpha Vantage."""

    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")

    if not api_key:
        return {"error": "Stock API key is not configured."}

    url = "https://www.alphavantage.co/query"

    try:
        response = requests.get(
            url,
            params={
                "function": "GLOBAL_QUOTE",
                "symbol": symbol.strip().upper(),
                "apikey": api_key,
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    except requests.RequestException:
        return {"error": "Unable to fetch stock data right now."}


client = MultiServerMCPClient(
    {
        "arith": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [
                str(Path(__file__).resolve().parent / "arith_server.py")
            ],
        },
        "expense": {
            "transport": "streamable_http",
            "url": "https://splendid-gold-dingo.fastmcp.app/mcp",
        },
    }
)

def load_mcp_tools() -> list[BaseTool]:
    try:
        tools = run_async(client.get_tools())

        # print("\n========== Loaded MCP Tools ==========")
        # for tool in tools:
        #     print(tool.name)
        # print("======================================\n")

        return tools

    except Exception as e:
        print("Failed to load MCP tools:", e)
        return []


mcp_tools = load_mcp_tools()
print("\n===== MCP TOOLS =====")
for tool in mcp_tools:
    print(tool.name)
print("=====================\n")

tools = [search_tool, get_stock_price, *mcp_tools]
llm_with_tools = llm.bind_tools(tools) if tools else llm

# -------------------
# 3. State
# -------------------
class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

# -------------------
# 4. Nodes
# -------------------
async def chat_node(state: ChatState):
    """LLM node that may answer or request a tool call."""
    messages = state["messages"]
    response = await llm_with_tools.ainvoke(messages)
    return {"messages": [response]}


tool_node = ToolNode(tools) if tools else None

# -------------------
# 5. Checkpointer
# -------------------





# -------------------
# 6. Graph
# -------------------
graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_edge(START, "chat_node")

if tool_node:
    graph.add_node("tools", tool_node)
    graph.add_conditional_edges("chat_node", tools_condition)
    graph.add_edge("tools", "chat_node")
else:
    graph.add_edge("chat_node", END)



# -------------------
# 7. Helper
# -------------------
async def _alist_threads(checkpointer):
    all_threads = set()

    async for checkpoint in checkpointer.alist(None):
        config = checkpoint.config.get("configurable", {})
        thread_id = config.get("thread_id")

        if thread_id:
            all_threads.add(thread_id)

    return list(all_threads)



@app.post("/chat")
async def chat(
    chat_request: ChatRequest,
    request: Request
):
    if not chat_request.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty."
        )

    if not chat_request.thread_id.strip():
        raise HTTPException(
            status_code=400,
            detail="Thread ID cannot be empty."
        )

    config = {
        "configurable": {
            "thread_id": chat_request.thread_id
        }
    }

    try:
        result = await request.app.state.chatbot.ainvoke(
            {
                "messages": [
                    HumanMessage(content=chat_request.message)
                ]
            },
            config=config
        )

        answer = result["messages"][-1].content

        return {
            "thread_id": chat_request.thread_id,
            "response": answer
        }

    except Exception as e:
        print("Chat error:", e)
        raise HTTPException(
            status_code=500,
            detail="Unable to process your message right now."
        )



@app.get("/threads")
async def get_threads(request: Request):
    try:
        thread_ids = await _alist_threads(
            request.app.state.checkpointer
        )

        return {
            "threads": thread_ids,
            "count": len(thread_ids)
        }

    except Exception as e:
        print("Thread retrieval error:", e)
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve conversations."
        )

