import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from '../context/ToastContext';

export default function ChatInterface({ sessionData, onEndSession, isEnding }) {
  const [messages, setMessages] = useState([
    { role: 'ai', text: sessionData.initialText }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);
  const { showToast } = useToast();
  
  const idleTimerRef = useRef(null);
  const INACTIVITY_LIMIT = 10000; 

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSilence = useCallback(async () => {
    if (loading || isEnding) return;
    
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/process_text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          session_id: sessionData.sessionId, 
          text: "", 
          is_silence: true 
        })
      });
      const data = await res.json();
      
      if (!isEnding) {
        setMessages(prev => [...prev, { role: 'ai', text: data.ai_text }]);
        if (data.finished) {
          setTimeout(() => { if(!isEnding) onEndSession(); }, 2000);
        }
      }
    } catch (e) {
      console.error("Silence handler error:", e);
    } finally {
      if (!isEnding) setLoading(false);
    }
  }, [loading, isEnding, sessionData.sessionId, onEndSession]);

  const resetIdleTimer = useCallback(() => {
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    
    if (!loading && !isEnding) {
      idleTimerRef.current = setTimeout(() => {
        handleSilence();
      }, INACTIVITY_LIMIT);
    }
  }, [loading, isEnding, handleSilence]);

  useEffect(() => {
    resetIdleTimer();
    return () => {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    };
  }, [input, loading, isEnding, resetIdleTimer]);

  const handleSend = async () => {
    if (!input.trim() || loading || isEnding) return;
    
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);

    const userText = input.trim();
    setMessages(prev => [...prev, { role: 'user', text: userText }]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/process_text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionData.sessionId, text: userText })
      });
      const data = await res.json();
      
      if (!isEnding) {
        setMessages(prev => [...prev, { role: 'ai', text: data.ai_text }]);

        if (data.finished) {
          showToast("Interview concluded by AI. Generating report...", "success");
          setTimeout(() => {
             if(!isEnding) onEndSession();
          }, 2000);
        }
      }
    } catch (e) {
      console.error(e);
      showToast("Failed to send message. Please try again.", "error");
    } finally {
      if (!isEnding) setLoading(false);
    }
  };

  return (
    <div className="chat-container">
      <div className="chat-history">
        {messages.map((msg, i) => (
          <div key={i} className={`chat-message-row ${msg.role}`}>
            <div className={`chat-bubble ${msg.role}`}>
              {msg.text}
            </div>
          </div>
        ))}
        {(loading || isEnding) && (
          <div className="chat-message-row ai">
            <div className="chat-bubble ai">
              <div className="typing-dots">
                <div className="dot"></div><div className="dot"></div><div className="dot"></div>
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-area">
        <input 
          type="text" 
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder={isEnding ? "Session Ended" : "Type your answer..."}
          disabled={loading || isEnding}
          className="input-field"
        />
        <button 
          onClick={handleSend}
          disabled={loading || isEnding || !input.trim()}
          className="chat-send-btn"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}