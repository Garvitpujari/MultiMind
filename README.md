MultiMind — Multi-Utility LangGraph Chatbot
A LangGraph chatbot with:
PDF RAG
DuckDuckGo web search
Calculator
Stock price lookup
Groq LLM
Persistent LangGraph memory
Persistent PDF embeddings
Supabase PostgreSQL + pgvector
FastAPI backend
Project structure
```text
multimind-chatbot/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example
│   └── schema.sql
├── .gitignore
└── README.md
```
Architecture
```text
Frontend / API Client
        |
        v
     FastAPI
        |
        v
    LangGraph
   /    |     \
 PDF   Web   Calculator
 RAG  Search   Stock
        |
        v
Supabase PostgreSQL
   |             |
   v             v
checkpoints   pgvector
              PDF chunks
        |
        v
      Groq
```
The old SQLite file:
```text
chatbot.db
```
is removed.
LangGraph checkpoints are persisted using `PostgresSaver`, while PDF chunks and embeddings are persisted in PostgreSQL using pgvector. LangGraph's current Postgres checkpointer requires `setup()` the first time it is used. See the official implementation/docs.
1. Create Supabase database
Create a Supabase project.
Open:
Supabase → Connect
Copy a PostgreSQL connection string suitable for your backend. Keep the password secret.
Supabase supports pgvector for storing and querying embeddings inside Postgres.
2. Configure environment variables
Copy:
```text
.env.example
```
to:
```text
.env
```
Then set:
```env
DATABASE_URL=your_supabase_postgresql_connection_string
GROQ_API_KEY=your_groq_key
ALPHAVANTAGE_API_KEY=your_alpha_vantage_key
```
DuckDuckGo does not require an API key in this implementation.
Do NOT upload `.env` to GitHub.
3. Install
From the `backend` folder:
```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```
4. Run
```powershell
uvicorn main:app --reload
```
Open:
```text
http://127.0.0.1:8000/docs
```
5. Test
Health
```text
GET /health
```
Upload PDF
```text
POST /documents/{user_id}/{thread_id}
```
Send the PDF as multipart form data with field:
```text
file
```
Chat
```text
POST /chat
```
Example:
```json
{
  "user_id": "user_001",
  "thread_id": "thread_001",
  "message": "What is this PDF about?"
}
```
Important architecture detail
The original project stored PDF retrievers in:
```python
_THREAD_RETRIEVERS = {}
```
That was RAM-only.
This version stores:
```text
PDF
 ↓
chunks
 ↓
embeddings
 ↓
Supabase PostgreSQL + pgvector
```
Therefore a backend restart does not erase the indexed PDF.
The LangGraph conversation state is separately persisted by:
```python
PostgresSaver
```
Multi-user note
The current `user_id` is an application-level identifier.
Before making this publicly accessible, add authentication and derive the user ID from the authenticated account rather than trusting a client-provided `user_id`.
The `/threads/{user_id}` endpoint is intentionally conservative: do not treat it as a secure user-isolation mechanism until authentication and an explicit user-to-thread ownership table are added.
GitHub
Commit:
```text
backend/main.py
backend/requirements.txt
backend/.env.example
backend/schema.sql
.gitignore
README.md
```
Do NOT commit:
```text
.env
```