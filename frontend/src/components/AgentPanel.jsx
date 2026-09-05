import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { chatWithAgent } from '../api'
import styles from './AgentPanel.module.css'

export default function AgentPanel({ isOpen, onClose, batchId }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef(null)
  
  // Clear conversation when batch changes
  useEffect(() => {
    setMessages([])
  }, [batchId])

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!input.trim() || !batchId || isLoading) return
    
    const userMessage = { role: 'user', content: input.trim() }
    const newMessages = [...messages, userMessage]
    setMessages(newMessages)
    setInput('')
    setIsLoading(true)
    
    try {
      const data = await chatWithAgent(batchId, newMessages)
      setMessages([...newMessages, ...data.messages])
      
    } catch (err) {
      console.error(err)
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: 'Sorry, I encountered an error. Please try again.' 
      }])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div className={styles.backdrop} onClick={onClose} />
      )}
      
      {/* Panel */}
      <div className={`${styles.panel} ${isOpen ? styles.open : ''}`}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <span className="material-symbols-outlined" style={{ color: 'var(--primary-container)' }}>chat</span>
            <h3>Ask Agent</h3>
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close agent panel">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>
        
        <div className={styles.messagesList}>
          {messages.length === 0 && (
            <div className={styles.emptyState}>
              <span className="material-symbols-outlined" style={{ fontSize: '32px', color: 'var(--outline)' }}>forum</span>
              <p>Ask a question about this reconciliation batch. E.g.</p>
              <ul>
                <li>"What is the match rate?"</li>
                <li>"Why is transaction TXN0001 unreconciled?"</li>
                <li>"Show me the top anomalies."</li>
              </ul>
            </div>
          )}
          
          {messages.map((msg, idx) => {
            // We only want to render user and assistant (final) messages.
            // Hide tool calls and tool results from the UI.
            if (msg.role === 'tool' || msg.tool_calls) {
              return null
            }
            if (!msg.content) return null;
            
            const isUser = msg.role === 'user'
            return (
              <div key={idx} className={`${styles.messageWrapper} ${isUser ? styles.userWrapper : styles.assistantWrapper}`}>
                {!isUser && (
                  <div className={styles.avatar}>
                    <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>robot_2</span>
                  </div>
                )}
                <div className={`${styles.bubble} ${isUser ? styles.userBubble : styles.assistantBubble}`}>
                  {isUser ? (
                    msg.content
                  ) : (
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  )}
                </div>
              </div>
            )
          })}
          
          {isLoading && (
            <div className={`${styles.messageWrapper} ${styles.assistantWrapper}`}>
              <div className={styles.avatar}>
                <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>robot_2</span>
              </div>
              <div className={`${styles.bubble} ${styles.assistantBubble} ${styles.loadingBubble}`}>
                <span className={styles.dot}></span>
                <span className={styles.dot}></span>
                <span className={styles.dot}></span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
        
        <form className={styles.inputArea} onSubmit={handleSubmit}>
          <input
            type="text"
            className={styles.input}
            placeholder={batchId ? "Ask a question..." : "Select a batch first"}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading || !batchId}
          />
          <button 
            type="submit" 
            className={styles.sendBtn}
            disabled={!input.trim() || isLoading || !batchId}
          >
            <span className="material-symbols-outlined">send</span>
          </button>
        </form>
      </div>
    </>
  )
}
