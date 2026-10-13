import asyncio
import hashlib
import os
import sys
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Optional, TypedDict

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langchain_groq import ChatGroq
from langchain_core.embeddings import Embeddings
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

load_dotenv()


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def get_authenticated_user(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Please log in.")

    token = authorization.split(" ", 1)[1]

    response = requests.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {token}",
        },
        timeout=10,
    )

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    return response.json()["id"]


def save_user_chat(user_id: str, thread_id: str, title: str):
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/user_chats",
        headers={
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        json={
            "user_id": user_id,
            "thread_id": thread_id,
            "title": title[:100],
        },
        timeout=10,
    )
    response.raise_for_status()

RAG_COLLECTION = "multimind_documents_jina_768"
_embeddings = None
_vector_store = None


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url




class JinaEmbeddings(Embeddings):
    """Generate embeddings using Jina's hosted API."""

    def __init__(self):
        self.api_key = os.getenv("JINA_API_KEY")
        self.model = "jina-embeddings-v2-base-en"
        self.api_url = "https://api.jina.ai/v1/embeddings"

        if not self.api_key:
            raise RuntimeError("JINA_API_KEY is missing from the environment.")

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = requests.post(
            self.api_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": texts,
            },
            timeout=60,
        )
        response.raise_for_status()

        data = response.json()["data"]
        data.sort(key=lambda item: item["index"])
        return [item["embedding"] for item in data]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # Small batches limit request size and memory usage.
        embeddings = []
        for start in range(0, len(texts), 16):
            embeddings.extend(self._embed(texts[start:start + 16]))
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]


def get_embeddings():
    """Initialize the API client without loading a local ML model."""
    global _embeddings

    if _embeddings is None:
        print("[RAG] Initializing Jina hosted embeddings...", flush=True)
        _embeddings = JinaEmbeddings()
        print("[RAG] Jina embedding client initialized.", flush=True)

    return _embeddings




def get_vector_store():
    global _vector_store
    if _vector_store is not None:
        return _vector_store
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing.")
    _vector_store = PGVector(
        embeddings=get_embeddings(),
        collection_name=RAG_COLLECTION,
        connection=normalize_database_url(database_url),
        use_jsonb=True,
    )
    return _vector_store


def ingest_pdf(file_bytes: bytes, thread_id: str, filename: Optional[str] = None) -> dict:
    """Extract, chunk, embed and persist a PDF, logging each stage."""
    if not file_bytes:
        raise ValueError("The uploaded PDF is empty.")
    thread_id = str(thread_id).strip()
    if not thread_id:
        raise ValueError("Thread ID cannot be empty.")

    filename = filename or "uploaded.pdf"
    document_id = str(uuid.uuid4())
    temp_path = None
    print(f"[PDF] Start: {filename!r}, {len(file_bytes)} bytes, thread={thread_id}", flush=True)

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name

        print("[PDF] Loading pages...", flush=True)
        documents = PyPDFLoader(temp_path).load()
        if not documents:
            raise ValueError("No readable pages were found in the PDF.")
        print(f"[PDF] Loaded {len(documents)} pages.", flush=True)

        chunks = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=150
        ).split_documents(documents)
        if not chunks:
            raise ValueError("No readable text was found. Scanned PDFs may require OCR.")
        print(f"[PDF] Created {len(chunks)} chunks.", flush=True)

        for index, chunk in enumerate(chunks):
            chunk.metadata["thread_id"] = thread_id
            chunk.metadata["filename"] = filename
            chunk.metadata["document_id"] = document_id
            chunk.metadata["chunk_index"] = index

        print("[PDF] Generating embeddings...", flush=True)
        vectors = get_embeddings().embed_documents([c.page_content for c in chunks])
        print(f"[PDF] Generated {len(vectors)} embeddings.", flush=True)

        chunk_ids = [
            hashlib.sha256(f"{thread_id}:{document_id}:{i}".encode()).hexdigest()
            for i in range(len(chunks))
        ]

        print("[PDF] Connecting to PGVector and saving...", flush=True)
        get_vector_store().add_embeddings(
            texts=[c.page_content for c in chunks],
            embeddings=vectors,
            metadatas=[c.metadata for c in chunks],
            ids=chunk_ids,
        )
        print(f"[PDF] SUCCESS: saved {len(chunks)} chunks for {filename!r}.", flush=True)
        return {
            "filename": filename,
            "pages": len(documents),
            "chunks": len(chunks),
            "thread_id": thread_id,
            "document_id": document_id,
        }
    except Exception as exc:
        print(f"[PDF ERROR] {type(exc).__name__}: {exc}", flush=True)
        raise
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
            print("[PDF] Temporary file cleaned up.", flush=True)


@tool
def rag_tool(query: str, config: RunnableConfig) -> dict:
    """Retrieve relevant passages from PDFs uploaded to this conversation."""
    thread_id = config.get("configurable", {}).get("thread_id")
    if not thread_id:
        return {"error": "Conversation thread ID is missing."}
    results = get_vector_store().similarity_search(
        query, k=4, filter={"thread_id": str(thread_id)}
    )
    if not results:
        return {"error": "No PDF is indexed for this conversation. Please upload a PDF first."}
    return {
        "query": query,
        "context": [d.page_content for d in results],
        "sources": [
            {"filename": d.metadata.get("filename"), "page": d.metadata.get("page")}
            for d in results
        ],
    }


# Dedicated event loop for MCP adapter calls.
_ASYNC_LOOP = asyncio.new_event_loop()


def _run_async_loop():
    asyncio.set_event_loop(_ASYNC_LOOP)
    _ASYNC_LOOP.run_forever()


threading.Thread(target=_run_async_loop, daemon=True).start()


def run_async(coro):
    return asyncio.run_coroutine_threadsafe(coro, _ASYNC_LOOP).result(timeout=30)


llm = ChatGroq(model="openai/gpt-oss-120b")
search_tool = DuckDuckGoSearchRun(region="us-en")


@tool
def get_stock_price(symbol: str) -> dict:
    """Fetch the latest stock quote using Alpha Vantage."""
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        return {"error": "Stock API key is not configured."}
    try:
        response = requests.get(
            "https://www.alphavantage.co/query",
            params={"function": "GLOBAL_QUOTE", "symbol": symbol.strip().upper(), "apikey": api_key},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        print(f"[STOCK ERROR] {type(exc).__name__}: {exc}", flush=True)
        return {"error": "Unable to fetch stock data right now."}


client = MultiServerMCPClient({
    "arith": {
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(Path(__file__).resolve().parent / "multimind_tools.py")],
    },
    "expense": {
        "transport": "streamable_http",
        "url": "https://splendid-gold-dingo.fastmcp.app/mcp",
    },
})


def load_mcp_tools() -> list[BaseTool]:
    try:
        result = run_async(client.get_tools())
        print(f"[MCP] Loaded {len(result)} tools.", flush=True)
        for item in result:
            print(f"[MCP] {item.name}", flush=True)
        return result
    except Exception as exc:
        print(f"[MCP ERROR] Failed to load MCP tools: {exc}", flush=True)
        return []


mcp_tools = load_mcp_tools()
tools = [search_tool, get_stock_price, rag_tool, *mcp_tools]
llm_with_tools = llm.bind_tools(tools)
tool_node = ToolNode(tools)



class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


async def chat_node(state: ChatState, config: RunnableConfig):
    system_prompt = """
    You are MultiMind, a helpful AI assistant that produces clean,
    professional, well-formatted responses.

    FORMATTING RULES:
    1. Use standard Markdown supported by chat interfaces.
    2. Use clear headings (## and ###) to organize longer answers.
    3. Use bullet points for lists and explanations.
    4. Use numbered lists for steps, procedures, and sequences.
    5. Use Markdown tables only when comparing structured information.
       Never put an entire explanation inside a table.
    6. Use **bold** for important terms and key takeaways.
    7. Use proper paragraph breaks between sections.
    8. NEVER output HTML tags such as <br>, <div>, or <p>.
    9. NEVER output Markdown syntax as escaped or literal text.
       Render headings, bold text, lists, and tables using valid Markdown.
    10. Avoid unnecessary repetition, excessive headings, and huge paragraphs.
    11. For summaries and study notes, preserve the source's meaning,
        terminology, and important details.
    12. For academic content, use this structure when appropriate:
        - Topic heading
        - Short explanation
        - Key points
        - Examples
        - Final takeaway
    13. For simple questions, answer directly without unnecessary sections.
    14. If retrieved PDF context is available, base document-specific
        answers on that context. Never invent facts from the PDF.
    15. If the retrieved context is insufficient, clearly state the limitation.

    Your goal is to make every response easy to read and visually organized.
    """

    thread_id = config.get("configurable", {}).get("thread_id", "")
    user_message = state["messages"][-1].content
    pdf_context = ""

    try:
        if thread_id and isinstance(user_message, str):
            print(
                f"[RAG] Searching documents for thread={thread_id}",
                flush=True,
            )

            results = await run_in_threadpool(
                lambda: get_vector_store().similarity_search(
                    user_message,
                    k=4,
                    filter={"thread_id": str(thread_id)},
                )
            )

            print(f"[RAG] Retrieved {len(results)} chunks", flush=True)

            if results:
                pdf_context = "\n\n".join(
                    f"Source: {doc.metadata.get('filename', 'PDF')}\n"
                    f"Page: {doc.metadata.get('page', 'Unknown')}\n"
                    f"{doc.page_content}"
                    for doc in results
                )

    except Exception as exc:
        print(
            f"[RAG ERROR] {type(exc).__name__}: {exc}",
            flush=True,
        )

    if pdf_context:
        system_prompt += (
            "\n\nRetrieved PDF context for this conversation:\n"
            f"{pdf_context}\n\n"
            "Answer questions about the uploaded PDF using this context."
        )
    else:
        system_prompt += (
            "\n\nNo matching PDF passages were retrieved for this message. "
            "Do not claim that a PDF was retrieved."
        )

    response = await llm_with_tools.ainvoke(
        [
            SystemMessage(content=system_prompt),
            *state["messages"],
        ],
        config=config,
    )

    return {"messages": [response]}

graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_node("tools", tool_node)
graph.add_edge(START, "chat_node")
graph.add_conditional_edges("chat_node", tools_condition)
graph.add_edge("tools", "chat_node")


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing.")
    async with AsyncPostgresSaver.from_conn_string(database_url) as checkpointer:
        await checkpointer.setup()
        app.state.checkpointer = checkpointer
        app.state.chatbot = graph.compile(checkpointer=checkpointer)
        print("[STARTUP] MultiMind API ready.", flush=True)
        yield


app = FastAPI(title="MultiMind API", lifespan=lifespan)
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys([
        "http://localhost:5173",
        "http://localhost:8501",
        "https://multi-mind-steel.vercel.app",
        frontend_url,
    ])),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "app": "MultiMind API"}


@app.post("/upload-pdf")
async def upload_pdfs(
    request: Request,
    thread_id: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload and index one PDF for a conversation."""
    thread_id = thread_id.strip()
    if not thread_id:
        await file.close()
        raise HTTPException(status_code=400, detail="Thread ID cannot be empty.")
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        await file.close()
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    try:
        print(f"[UPLOAD] Received {file.filename!r}; thread={thread_id}", flush=True)
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")
        metadata = await run_in_threadpool(ingest_pdf, file_bytes, thread_id, file.filename)
        print(f"[UPLOAD] Completed {file.filename!r}", flush=True)
        return {"message": "PDF indexed successfully.", "thread_id": thread_id, "document": metadata}
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[UPLOAD ERROR] {type(exc).__name__}: {exc}", flush=True)
        raise HTTPException(
            status_code=500,
            detail=f"Unable to process the PDF ({type(exc).__name__}). Check Render logs.",
        ) from exc
    finally:
        await file.close()


class ChatRequest(BaseModel):
    message: str
    thread_id: str


@app.post("/chat")
async def chat(chat_request: ChatRequest, request: Request):
    if not chat_request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    if not chat_request.thread_id.strip():
        raise HTTPException(status_code=400, detail="Thread ID cannot be empty.")
    config = {"configurable": {"thread_id": chat_request.thread_id.strip()}}
    try:
        result = await request.app.state.chatbot.ainvoke(
            {"messages": [HumanMessage(content=chat_request.message)]}, config=config
        )
        return {"thread_id": chat_request.thread_id, "response": result["messages"][-1].content}
    except Exception as exc:
        print(f"[CHAT ERROR] {type(exc).__name__}: {exc}", flush=True)
        raise HTTPException(status_code=500, detail="Unable to process your message. Check Render logs.") from exc


async def _alist_threads(checkpointer):
    thread_ids = set()
    async for checkpoint in checkpointer.alist(None):
        thread_id = checkpoint.config.get("configurable", {}).get("thread_id")
        if thread_id:
            thread_ids.add(thread_id)
    return sorted(thread_ids)


@app.get("/threads")
async def get_threads(request: Request):
    try:
        thread_ids = await _alist_threads(request.app.state.checkpointer)
        return {"threads": thread_ids, "count": len(thread_ids)}
    except Exception as exc:
        print(f"[THREADS ERROR] {type(exc).__name__}: {exc}", flush=True)
        raise HTTPException(status_code=500, detail="Unable to retrieve conversations.") from exc


@app.get("/threads/{thread_id}")
async def get_thread(thread_id: str, request: Request):
    try:
        config = {
            "configurable": {
                "thread_id": thread_id
            }
        }

        state = await request.app.state.chatbot.aget_state(config)

        if not state or not state.values:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found."
            )

        messages = []

        for index, message in enumerate(
            state.values.get("messages", [])
        ):
            if message.type not in ("human", "ai"):
                continue

            content = message.content

            if not isinstance(content, str):
                content = str(content)

            messages.append({
                "id": message.id or f"{thread_id}-{index}",
                "role": (
                    "user" if message.type == "human"
                    else "assistant"
                ),
                "content": content
            })

        return {
            "thread_id": thread_id,
            "messages": messages
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(
            f"[THREAD ERROR] {type(exc).__name__}: {exc}",
            flush=True
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve conversation."
        ) from exc
