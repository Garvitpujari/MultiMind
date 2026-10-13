## Challenges Faced and Solutions

Building MultiMind involved several challenges across AI orchestration, document retrieval, database integration, authentication, and deployment.

### 1. LangGraph State and Conversation Persistence

**Challenge:** Managing conversation state across multiple chat threads and ensuring that previous conversations could be restored correctly.

**What we learned:**
- LangGraph requires a consistent state schema and correctly configured graph nodes.
- Checkpointing must use the appropriate `thread_id` to maintain separate conversations.
- Graph state, checkpoint identifiers, and user-facing chat metadata serve different purposes.

**Approach:** We structured the chatbot using LangGraph state management and thread-based checkpointing to support multiple conversations.

### 2. PDF Processing and RAG Pipeline

**Challenge:** Enabling the chatbot to answer questions using uploaded PDF documents instead of relying only on the language model's general knowledge.

**Difficulties encountered:**
- Extracting and splitting long documents into manageable chunks.
- Retrieving relevant passages for each user question.
- Keeping retrieved document context associated with the correct conversation.
- Handling document ingestion and retrieval errors without crashing the chatbot.

**Approach:** We implemented a RAG pipeline using document chunking, Jina embeddings, PostgreSQL with PGVector, and similarity search. Retrieved passages are added to the model's system context when relevant documents are found.

### 3. Embedding and Vector Database Integration

**Challenge:** Integrating embedding generation with vector storage while keeping the embedding dimensions and collection configuration consistent.

**Difficulties encountered:**
- Configuring the embedding service and API credentials.
- Ensuring stored vectors and query embeddings use the same embedding model and dimensions.
- Filtering document retrieval using conversation metadata.

**Approach:** We used Jina embeddings with a dedicated PGVector collection, `multimind_documents_jina_768`, and conversation-level metadata filtering.

### 4. LangGraph Node and Prompt Debugging

**Challenge:** Debugging errors involving graph nodes, prompt construction, and asynchronous model execution.

**Difficulties encountered:**
- Ensuring graph nodes and state definitions were configured correctly.
- Handling exceptions during vector similarity search.
- Fixing a `system_prompt` initialization issue that caused an `UnboundLocalError` during chat execution.

**Approach:** We corrected the prompt initialization flow so the system prompt exists before retrieval begins, while keeping retrieval errors separate from the prompt setup.

### 5. Frontend and Backend Integration

**Challenge:** Connecting the React frontend with the FastAPI backend across local development and deployed environments.

**Difficulties encountered:**
- Configuring the backend API URL through environment variables.
- Setting up CORS for the deployed frontend.
- Handling PDF uploads and chat requests through separate endpoints.
- Diagnosing failures that occurred after successful document ingestion.

**Approach:** We configured the frontend to communicate with the deployed FastAPI service and used backend logs and API documentation to debug requests.

### 6. Authentication and Conversation Ownership

**Challenge:** Integrating Supabase Authentication with a backend that also maintains LangGraph conversation threads.

**Key lesson:** Authentication and conversation persistence are separate concerns. A valid login does not automatically guarantee that a user can access only their own conversations.

**Current improvement area:** Enforcing authentication and ownership checks across chat, PDF upload, and conversation-history endpoints, while persisting user-to-thread mappings in Supabase.

### 7. Chat Titles and History Ordering

**Challenge:** The sidebar displays generic titles such as "Previous conversation" because LangGraph checkpoint thread IDs do not inherently contain meaningful conversation titles.

**Current improvement area:**
- Generate descriptive titles from the first user message.
- Store titles and creation timestamps in Supabase.
- Load chat history in a consistent chronological order.
- Preserve titles and ordering after page refreshes and new sessions.

### 8. Deployment and Environment Configuration

**Challenge:** Deploying the frontend and backend separately while ensuring both services use the correct configuration.

**Difficulties encountered:**
- Managing environment variables across local development and deployment.
- Configuring Supabase, Groq, Jina, and database credentials.
- Debugging backend errors using deployment logs.
- Ensuring private credentials remain on the backend.

**Approach:** We deployed the React frontend on Vercel and the FastAPI backend on Render, with environment-specific configuration for API communication and external services.

### Key Takeaways

The development of MultiMind reinforced several important engineering lessons:

- **Debug systematically:** Use stack traces, backend logs, and isolated tests to locate the source of failures.
- **Keep AI pipelines consistent:** Embedding models, vector dimensions, database collections, and retrieval metadata must agree.
- **Separate responsibilities:** Authentication, conversation state, document storage, and chat metadata require distinct handling.
- **Design for multiple users:** Thread identifiers alone are not sufficient for secure user-level access control.
- **Test the complete workflow:** Successful PDF ingestion does not necessarily mean retrieval and question answering work correctly end to end.
- **Treat deployment as part of development:** Environment variables, CORS, database connectivity, and API configuration are essential to a reliable application.
