import React, { useState, useEffect, useCallback, memo } from 'react';
import { Clock } from 'lucide-react';
import VoiceInterface from './VoiceInterface';
import ChatInterface from './ChatInterface';
import { API_URL } from '../config';
import { useToast } from '../context/ToastContext';

const MemoizedVoiceInterface = memo(VoiceInterface);
const MemoizedChatInterface = memo(ChatInterface);

export default function LiveSession({ sessionData, interviewMode, onEnd }) {
  const [elapsed, setElapsed] = useState(0);
  const [isEnding, setIsEnding] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    const timer = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const formatTime = (secs) => {
    const m = Math.floor(secs / 60).toString().padStart(2, '0');
    const s = (secs % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  const handleEndSession = useCallback(async () => {
    if (isEnding) return; 
    setIsEnding(true);
    showToast("Ending session and generating report...", "info");
    
    console.log("Ending session, fetching report for:", sessionData.sessionId);

    try {
      const res = await fetch(`${API_URL}/generate_report/${sessionData.sessionId}`);
      
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`Report generation failed: ${res.status} ${errText}`);
      }
      
      const data = await res.json();
      console.log("Report data received:", data);
      showToast("Report generated successfully!", "success");
      onEnd(data);
    } catch (e) {
      console.error("Report Error:", e);
      showToast("Failed to generate report. Please click 'End Interview Early' again to retry.", "error");
      setIsEnding(false);
    }
  }, [isEnding, sessionData.sessionId, onEnd, showToast]);

  return (
    <div style={{width: '100%'}}>
      <div className="session-header">
        <div className="timer">
          <Clock size={18} />
          <span>{formatTime(elapsed)}</span>
        </div>
        <div className="live-badge">
          Live Session
        </div>
      </div>

      {interviewMode === 'voice' ? (
        <MemoizedVoiceInterface 
          sessionData={sessionData} 
          onEndSession={handleEndSession} 
          isEnding={isEnding}
        />
      ) : (
        <MemoizedChatInterface 
          sessionData={sessionData} 
          onEndSession={handleEndSession} 
          isEnding={isEnding}
        />
      )}

      <div style={{textAlign: 'center'}}>
        <button 
          onClick={handleEndSession}
          disabled={isEnding}
          className="btn btn-danger"
        >
          {isEnding ? 'Generating Report...' : 'End Interview Early'}
        </button>
      </div>
    </div>
  );
}