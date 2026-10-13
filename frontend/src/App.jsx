import { useEffect, useRef, useState } from 'react'
import './App.css'
import Auth from './components/Auth'
import { supabase } from './library/supabase'



const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  'https://multimind-x5eq.onrender.com'


function App() {

const [session, setSession] = useState(null)
const [authLoading, setAuthLoading] = useState(true)
 const [showAuth, setShowAuth] = useState(false)

useEffect(() => {
  supabase.auth.getSession().then(({ data, error }) => {
    if (error) {
      console.error('Could not retrieve session:', error.message)
    }

    setSession(data?.session ?? null)
    setAuthLoading(false)
  })

  const {
    data: { subscription },
  } = supabase.auth.onAuthStateChange((_event, session) => {
    setSession(session)
    setAuthLoading(false)
  })

  return () => subscription.unsubscribe()
}, [])
  const [chats, setChats] = useState([])
//   setChats([
//   { id: 'chat-1', title: 'Learn Python' }
// ])
  const [activeChatId, setActiveChatId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState([])
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [isLoading, setIsLoading] = useState(false)

  const fileInputRef = useRef(null)

  function startNewChat() {
    setActiveChatId(null)
    setMessages([])
    setInput('')
    setAttachments([])
  }

  function selectChat(chat) {
    setActiveChatId(chat.id)
    setMessages(chat.messages ?? [])
    setInput('')
    setAttachments([])
  }

  function handleFileSelect(event) {
  const selectedFiles = Array.from(event.target.files ?? [])
  const pdfFiles = selectedFiles.filter((file) =>
    file.name.toLowerCase().endsWith('.pdf')
  )

  if (pdfFiles.length !== selectedFiles.length) {
    alert('Only PDF files are supported currently.')
  }

  setAttachments((current) => [...current, ...pdfFiles])
  event.target.value = ''
}

  function removeAttachment(index) {
    setAttachments((current) =>
      current.filter((_, currentIndex) => currentIndex !== index),
    )
  }

  async function handleSubmit(event) {
     event.preventDefault()

  const text = input.trim()

  if ((!text && attachments.length === 0) || isLoading) {
    return
  }

  const threadId = activeChatId || crypto.randomUUID()
  const filesToUpload = [...attachments]

  const userMessage =
    text ||
    `Please summarize and analyze the uploaded PDF${
      filesToUpload.length > 1 ? 's' : ''
    }.`

  const userEntry = {
    id: crypto.randomUUID(),
    role: 'user',
    content: userMessage,
    files: filesToUpload.map((file) => file.name),
  }

  setActiveChatId(threadId)
  setMessages((current) => [...current, userEntry])
  setInput('')
  setAttachments([])
  setIsLoading(true)

  try {
    // 1. Upload each selected PDF to the backend.
    for (const file of filesToUpload) {
      const formData = new FormData()

      formData.append('thread_id', threadId)
      formData.append('file', file)

      const uploadResponse = await fetch(
        `${API_BASE_URL}/upload-pdf`,
        {
          method: 'POST',
          body: formData,
        }
      )

      if (!uploadResponse.ok) {
        const errorData = await uploadResponse
          .json()
          .catch(() => ({}))

        throw new Error(
          errorData.detail || `Failed to upload ${file.name}`
        )
      }
    }

    // 2. Send the message to the AI backend.
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: userMessage,
        thread_id: threadId,
      }),
    })

    const data = await response.json()

    if (!response.ok) {
      throw new Error(
        data.detail || 'The chat request failed.'
      )
    }

    // 3. Display the AI's response.
    const assistantMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: data.response,
    }

    setMessages((current) => [
      ...current,
      assistantMessage,
    ])

    // 4. Save the conversation in the sidebar state.
    setChats((current) => {
      const existingChat = current.find(
        (chat) => chat.id === threadId
      )

      const updatedChat = {
        id: threadId,
        title: userMessage.slice(0, 45) || 'New conversation',
        messages: [
          ...(existingChat?.messages ?? []),
          userEntry,
          assistantMessage,
        ],
      }

      return existingChat
        ? current.map((chat) =>
            chat.id === threadId ? updatedChat : chat
          )
        : [updatedChat, ...current]
    })
  } catch (error) {
    console.error('MultiMind request failed:', error)

    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `Request failed: ${error.message}. Please try again.`,
      },
    ])
  } finally {
    setIsLoading(false)
  }
  }

  





  return (
    
    <div className="app-shell">
      {sidebarOpen && (
        <aside className="sidebar">
          <div className="sidebar-header">
            <button
              className="brand"
              type="button"
              onClick={startNewChat}
              aria-label="MultiMind home"
            >
              <span className="brand-mark">M</span>
              <span>MultiMind</span>
            </button>

            <button
              className="icon-button sidebar-close"
              type="button"
              aria-label="Close sidebar"
              onClick={() => setSidebarOpen(false)}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <rect x="3.5" y="4" width="17" height="16" rx="2" />
                <path d="M9 4v16" />
              </svg>
            </button>
          </div>

          <button
            className="new-chat-button"
            type="button"
            onClick={startNewChat}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"> // dont read this 
              <path d="M12 5v14M5 12h14" />
            </svg>
            <span>New chat</span>
          </button>

          <div className="chat-history">
            <p className="sidebar-label">Your conversations</p>

            {chats.length === 0 ? (
              <div className="empty-history">
                <span className="history-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24">
                    <path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l1.8-3.6A7.5 7.5 0 1 1 20 11.5Z" />
                  </svg>
                </span>
                <p>Your conversations will appear here.</p>
              </div>
            ) : (
              <div className="chat-list">
                {chats.map((chat) => (
                  <button
                    className={`chat-list-item ${
                      activeChatId === chat.id ? 'active' : ''
                    }`}
                    key={chat.id}
                    type="button"
                    onClick={() => selectChat(chat)}
                    title={chat.title}
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l1.8-3.6A7.5 7.5 0 1 1 20 11.5Z" />
                    </svg>
                    <span>{chat.title}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="sidebar-footer">
            <div className="user-avatar" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <circle cx="12" cy="8" r="3.5" />
                <path d="M5 20a7 7 0 0 1 14 0" />
              </svg>
            </div>

            
          <div className="user-details">
            <strong>
              {session?.user?.email ? 'My account' : 'Guest'}
            </strong>

            <span>
              {session?.user?.email || 'Sign in to get started'}
            </span>
          </div>


            <button
              className="icon-button account-menu-button"
              type="button"
              aria-label="Account options"
              onClick={() => setShowAuth(true)}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="5" cy="12" r="1" />
                <circle cx="12" cy="12" r="1" />
                <circle cx="19" cy="12" r="1" />
              </svg>
            </button>
          </div>
        </aside>
      )}

      <main className="main-panel">
        <header className="topbar">
          <div className="topbar-left">
            {!sidebarOpen && (
              <button
                className="icon-button"
                type="button"
                aria-label="Open sidebar"
                onClick={() => setSidebarOpen(true)}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <rect x="3.5" y="4" width="17" height="16" rx="2" />
                  <path d="M9 4v16" />
                </svg>
              </button>
            )}

            <div className="model-indicator">
              <span className="status-dot" />
              <span>MultiMind AI</span>
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m8 10 4 4 4-4" />
              </svg>
            </div>
          </div>

          <button
            className="login-button"
            type="button"
            onClick={() => setShowAuth(true)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
              <path d="M10 17l5-5-5-5M15 12H3" />
            </svg>
            <span>
              {session?.user?.email || 'Log in / Sign up'}
            </span>
          </button>
        </header>

        <section className="conversation">
          {messages.length === 0 ? (
            <div className="welcome">
              <div className="welcome-icon" aria-hidden="true">
                <svg viewBox="0 0 48 48">
                  <path d="M24 4 28.5 18.5 43 23l-14.5 4.5L24 42l-4.5-14.5L5 23l14.5-4.5L24 4Z" />
                  <path d="m39 31 2 6 6 2-6 2-2 6-2-6-6-2 6-2 2-6Z" />
                </svg>
              </div>

              <p className="welcome-eyebrow">YOUR PERSONAL AI WORKSPACE</p>
              <h1>What can I help you with?</h1>
              <p className="welcome-description">
                Ask questions, explore ideas, work with documents,
                and get things done in one place.
              </p>

              <div className="suggestion-grid">
                <button
                  className="suggestion-card"
                  type="button"
                  onClick={() => setInput('')}
                >
                  <span className="suggestion-icon learn-icon">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M12 3 3 8l9 5 9-5-9-5Z" />
                      <path d="m6 10 6 3 6-3M5 12v5l7 4 7-4v-5" />
                    </svg>
                  </span>
                  <span className="suggestion-text">
                    <strong>Learn something</strong>
                    <small>Understand topics step by step</small>
                  </span>
                  <span className="suggestion-arrow">↗</span>
                </button>

                <button
                  className="suggestion-card"
                  type="button"
                  onClick={() => setInput('')}
                >
                  <span className="suggestion-icon code-icon">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="m8 7-5 5 5 5M16 7l5 5-5 5M14 4l-4 16" />
                    </svg>
                  </span>
                  <span className="suggestion-text">
                    <strong>Code and create</strong>
                    <small>Build projects and debug code</small>
                  </span>
                  <span className="suggestion-arrow">↗</span>
                </button>

                <button
                  className="suggestion-card"
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <span className="suggestion-icon document-icon">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10Z" />
                      <path d="M13 3v7h7M8 14h8M8 17h8" />
                    </svg>
                  </span>
                  <span className="suggestion-text">
                    <strong>Explore documents</strong>
                    <small>Prepare a file for analysis</small>
                  </span>
                  <span className="suggestion-arrow">↗</span>
                </button>

                <button
                  className="suggestion-card"
                  type="button"
                  onClick={() => setInput('')}
                >
                  <span className="suggestion-icon research-icon">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <circle cx="10.5" cy="10.5" r="6.5" />
                      <path d="m16 16 5 5M8 10.5h5M10.5 8v5" />
                    </svg>
                  </span>
                  <span className="suggestion-text">
                    <strong>Research and explore</strong>
                    <small>Investigate ideas and questions</small>
                  </span>
                  <span className="suggestion-arrow">↗</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="message-list">
              {messages.map((message) => (
                <article
                  className={`message ${message.role}`}
                  key={message.id}
                >
                  <div className="message-avatar">
                    {message.role === 'user' ? 'U' : 'M'}
                  </div>

                  <div className="message-content">
                    <strong>
                      {message.role === 'user' ? 'You' : 'MultiMind'}
                    </strong>
                    {message.content && <p>{message.content}</p>}

                    {message.files?.map((file, index) => (
                      <div className="attached-file" key={`${file}-${index}`}>
                        <span>↗</span>
                        {file}
                      </div>
                    ))}
                  </div>
                </article>
              ))}

              {isLoading && (
                <div className="loading-indicator" role="status">
                  <span className="loading-dots"><i /><i /><i /></span>
                  MultiMind is thinking...
                </div>
              )}
            </div>
          )}
        </section>

        <footer className="composer-area">
          <form className="composer" onSubmit={handleSubmit}>
            {attachments.length > 0 && (
              <div className="attachment-list">
                {attachments.map((file, index) => (
                  <div
                    className="attachment-chip"
                    key={`${file.name}-${file.size}-${index}`}
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z" />
                      <path d="M14 3v6h6" />
                    </svg>
                    <span title={file.name}>{file.name}</span>
                    <button
                      type="button"
                      aria-label={`Remove ${file.name}`}
                      onClick={() => removeAttachment(index)}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}

            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (
                  event.key === 'Enter' &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing
                ) {
                  event.preventDefault()
                  event.currentTarget.form.requestSubmit()
                }
              }}
              placeholder="Message MultiMind..."
              aria-label="Message MultiMind"
              rows={2}
            />

            <div className="composer-toolbar">
              <div className="composer-tools">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  hidden
                  accept=".pdf,application/pdf"
                  onChange={handleFileSelect}
                />

                <button
                  className="attach-button"
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12 5v14M5 12h14" />
                  </svg>
                  <span>Attach files</span>
                </button>
              </div>

              <button
                className="send-button"
                type="submit"
                disabled={
                  isLoading ||
                  (!input.trim() && attachments.length === 0)
                }
                aria-label="Send message"
                title="Send message"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 19V5M5 12l7-7 7 7" />
                </svg>
              </button>
            </div>
          </form>

          <p className="disclaimer">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 11v5M12 8h.01" />
            </svg>
            AI can make mistakes. Verify important information.
          </p>
        </footer>
      
      </main>

      {showAuth && (
        <div
          className="auth-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setShowAuth(false)
            }
          }}
        >
          <div
            className="auth-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Log in or sign up"
          >
            <button
              type="button"
              className="auth-close"
              aria-label="Close authentication"
              onClick={() => setShowAuth(false)}
            >
              ×
            </button>

            <Auth />
          </div>
        </div>
      )}
    </div>
  )
}

export default App
