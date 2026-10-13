import asyncio
import hashlib
import os
import sys
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
# from typing import Annotated, Optional, TypedDict
from typing import Annotated, Optional, TypedDict
from fastapi import UploadFile


import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

load_dotenv()

# ============================================================
# Persistent PostgreSQL RAG storage
# ============================================================

RAG_COLLECTION = "multimind_documents"

_embeddings = None
_vector_store = None


def get_embeddings():
    """Load the embedding model once per backend process."""
    global _embeddings

    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

    return _embeddings


def get_vector_store():
    """Return the PGVector interface for the persistent document collection."""
    global _vector_store

    if _vector_store is not None:
        return _vector_store

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing.")

    # Normalize common PostgreSQL URLs for psycopg 3 / SQLAlchemy.
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )

    _vector_store = PGVector(
        embeddings=get_embeddings(),
        collection_name=RAG_COLLECTION,
        connection=database_url,
        use_jsonb=True,
    )
    return _vector_store


def ingest_pdf(
    file_bytes: bytes,
    thread_id: str,
    filename: Optional[str] = None,
) -> dict:
    """
    Extract and split a PDF, create embeddings, and persist them.
    Each upload gets a document_id, so multiple PDFs can be attached
    to the same conversation without deleting the other PDFs.
    """
    if not file_bytes:
        raise ValueError("The uploaded PDF is empty.")

    thread_id = str(thread_id).strip()
    if not thread_id:
        raise ValueError("Thread ID cannot be empty.")

    stored_filename = filename or "uploaded.pdf"
    document_id = str(uuid.uuid4())
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name

        documents = PyPDFLoader(temp_path).load()
        if not documents:
            raise ValueError("No readable pages were found in the PDF.")

        chunks = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=150,
        ).split_documents(documents)

        if not chunks:
            raise ValueError("No readable text was found in the PDF.")

        for index, chunk in enumerate(chunks):
            chunk.metadata["thread_id"] = thread_id
            chunk.metadata["filename"] = stored_filename
            chunk.metadata["document_id"] = document_id
            chunk.metadata["chunk_index"] = index

        # Generate embeddings once, then persist those exact vectors.
        vectors = get_embeddings().embed_documents(
            [chunk.page_content for chunk in chunks]
        )

        chunk_ids = [
            hashlib.sha256(
                f"{thread_id}:{document_id}:{index}".encode("utf-8")
            ).hexdigest()
            for index in range(len(chunks))
        ]

        store = get_vector_store()
        store.add_embeddings(
            texts=[chunk.page_content for chunk in chunks],
            embeddings=vectors,
            metadatas=[chunk.metadata for chunk in chunks],
            ids=chunk_ids,
        )

        return {
            "filename": stored_filename,
            "pages": len(documents),
            "chunks": len(chunks),
            "thread_id": thread_id,
            "document_id": document_id,
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@tool
def rag_tool(query: str, config: RunnableConfig) -> dict:
    """Retrieve relevant passages from all PDFs uploaded to this conversation."""
    configurable = config.get("configurable", {})
    thread_id = configurable.get("thread_id")

    if not thread_id:
        return {"error": "Conversation thread ID is missing."}

    store = get_vector_store()
    results = store.similarity_search(
        query,
        k=4,
        filter={"thread_id": str(thread_id)},
    )

    if not results:
        return {
            "error": (
                "No PDF is indexed for this conversation. "
                "Please upload one or more PDFs first."
            )
        }

    return {
        "query": query,
        "context": [document.page_content for document in results],
        "sources": [
            {
                "filename": document.metadata.get("filename"),
                "page": document.metadata.get("page"),
            }
            for document in results
        ],
    }


# ============================================================
# FastAPI app and routes
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing.")

    async with AsyncPostgresSaver.from_conn_string(database_url) as checkpointer:
        await checkpointer.setup()
        app.state.checkpointer = checkpointer
        app.state.chatbot = graph.compile(checkpointer=checkpointer)
        yield


app = FastAPI(title="MultiMind API", lifespan=lifespan)

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8501",
        frontend_url,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "app": "MultiMind API"}


# @app.post("/upload-pdf")
# async def upload_pdfs(
#     thread_id: str = Form(...),
#     files: list[UploadFile] = File(...),
# ):
#     """Upload and index one or more PDFs for the specified conversation."""
#     thread_id = thread_id.strip()
#     if not thread_id:
#         raise HTTPException(status_code=400, detail="Thread ID cannot be empty.")

#     if not files:
#         raise HTTPException(status_code=400, detail="Upload at least one PDF.")

#     if len(files) > 10:
#         raise HTTPException(
#             status_code=400,
#             detail="You can upload at most 10 PDFs per request.",
#         )

#     indexed = []
#     try:
#         for uploaded_file in files:
#             if not uploaded_file.filename or not uploaded_file.filename.lower().endswith(".pdf"):
#                 raise HTTPException(
#                     status_code=400,
#                     detail=f"{uploaded_file.filename or 'A file'} is not a PDF.",
#                 )

#             file_bytes = await uploaded_file.read()
#             if not file_bytes:
#                 raise HTTPException(
#                     status_code=400,
#                     detail=f"{uploaded_file.filename} is empty.",
#                 )

#             metadata = await run_in_threadpool(
#                 ingest_pdf,
#                 file_bytes,
#                 thread_id,
#                 uploaded_file.filename,
#             )
#             indexed.append(metadata)

#         return {
#             "message": f"Successfully indexed {len(indexed)} PDF(s).",
#             "thread_id": thread_id,
#             "documents": indexed,
#         }
#     except HTTPException:
#         raise
#     except Exception as exc:
#         print("PDF ingestion error:", exc)
#         raise HTTPException(
#             status_code=500,
#             detail="Unable to process one or more PDFs.",
#         ) from exc
#     finally:
#         for uploaded_file in files:
#             await uploaded_file.close()




@app.post("/upload-pdf")
async def upload_pdfs(
    thread_id: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload and index one PDF for a conversation."""

    thread_id = thread_id.strip()

    if not thread_id:
        raise HTTPException(
            status_code=400,
            detail="Thread ID cannot be empty."
        )

    try:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail="Please upload a PDF file."
            )

        file_bytes = await file.read()

        if not file_bytes:
            raise HTTPException(
                status_code=400,
                detail="The uploaded PDF is empty."
            )

        metadata = await run_in_threadpool(
            ingest_pdf,
            file_bytes,
            thread_id,
            file.filename,
        )

        return {
            "message": "PDF indexed successfully.",
            "thread_id": thread_id,
            "document": metadata,
        }

    except HTTPException:
        raise
    except Exception as exc:
        print("PDF ingestion error:", exc)
        raise HTTPException(
            status_code=500,
            detail="Unable to process the PDF."
        ) from exc
    finally:
        await file.close()


class ChatRequest(BaseModel):
    message: str
    thread_id: str


# ============================================================
# Async loop used by the MCP adapter
# ============================================================

_ASYNC_LOOP = asyncio.new_event_loop()
_ASYNC_THREAD = threading.Thread(
    target=_ASYNC_LOOP.run_forever,
    daemon=True,
)
_ASYNC_THREAD.start()


def _submit_async(coro):
    return asyncio.run_coroutine_threadsafe(coro, _ASYNC_LOOP)


def run_async(coro):
    return _submit_async(coro).result()


def submit_async_task(coro):
    """Schedule a coroutine on the backend event loop."""
    return _submit_async(coro)


# ============================================================
# LLM and tools
# ============================================================

llm = ChatGroq(model="openai/gpt-oss-120b")
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
                str(Path(__file__).resolve().parent / "multimind_tools.py")
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
        return run_async(client.get_tools())
    except Exception as exc:
        print("Failed to load MCP tools:", exc)
        return []


mcp_tools = load_mcp_tools()
print("\n===== MCP TOOLS =====")
for mcp_tool in mcp_tools:
    print(mcp_tool.name)
print("=====================\n")

tools = [search_tool, get_stock_price, rag_tool, *mcp_tools]
llm_with_tools = llm.bind_tools(tools)
tool_node = ToolNode(tools)


# ============================================================
# LangGraph
# ============================================================

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


async def chat_node(state: ChatState, config: RunnableConfig):
    system_message = SystemMessage(
        content=(
            "You are MultiMind, a helpful AI assistant. "
            "For questions about PDFs uploaded to the current conversation, "
            "use rag_tool and base your answer on its retrieved context. "
            "If no PDF is available, ask the user to upload one. "
            "Do not invent document facts. Use web search for current external "
            "information when appropriate, and use other tools when useful."
        )
    )
    response = await llm_with_tools.ainvoke(
        [system_message, *state["messages"]],
        config=config,
    )
    return {"messages": [response]}


graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_node("tools", tool_node)
graph.add_edge(START, "chat_node")
graph.add_conditional_edges("chat_node", tools_condition)
graph.add_edge("tools", "chat_node")


async def _alist_threads(checkpointer):
    all_threads = set()
    async for checkpoint in checkpointer.alist(None):
        configurable = checkpoint.config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        if thread_id:
            all_threads.add(thread_id)
    return list(all_threads)


@app.post("/chat")
async def chat(chat_request: ChatRequest, request: Request):
    if not chat_request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    if not chat_request.thread_id.strip():
        raise HTTPException(status_code=400, detail="Thread ID cannot be empty.")

    config = {"configurable": {"thread_id": chat_request.thread_id}}
    try:
        result = await request.app.state.chatbot.ainvoke(
            {"messages": [HumanMessage(content=chat_request.message)]},
            config=config,
        )
        answer = result["messages"][-1].content
        return {
            "thread_id": chat_request.thread_id,
            "response": answer,
        }
    except Exception as exc:
        print("Chat error:", exc)
        raise HTTPException(
            status_code=500,
            detail="Unable to process your message right now.",
        ) from exc


@app.get("/threads")
async def get_threads(request: Request):
    try:
        thread_ids = await _alist_threads(request.app.state.checkpointer)
        return {"threads": thread_ids, "count": len(thread_ids)}
    except Exception as exc:
        print("Thread retrieval error:", exc)
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve conversations.",
        ) from exc
