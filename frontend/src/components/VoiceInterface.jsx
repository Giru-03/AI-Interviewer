import React, { useState, useEffect, useRef } from 'react';
import { API_URL } from '../config';
import { useToast } from '../context/ToastContext';

export default function VoiceInterface({ sessionData, onEndSession, isEnding }) {
  const [status, setStatus] = useState('speaking');
  const [text, setText] = useState(sessionData.initialText);
  const [userTranscript, setUserTranscript] = useState([]);
  const { showToast } = useToast();
  
  const audioRef = useRef(new Audio());
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const mountedRef = useRef(true);
  
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const silenceTimerRef = useRef(null);
  const animationFrameRef = useRef(null);
  const maxTimeRef = useRef(null); 

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (isEnding) {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = "";
      }
      stopRecording();
    }
  }, [isEnding]);

  useEffect(() => {
    return () => {
        if(animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
        if(silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
        if(maxTimeRef.current) clearTimeout(maxTimeRef.current);
        if(audioCtxRef.current) audioCtxRef.current.close();
    }
  }, []);

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      if (mountedRef.current) setStatus('processing');
    }
    if(animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
    if(silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    if(maxTimeRef.current) clearTimeout(maxTimeRef.current);
  };

  const detectSilence = (analyser) => {
      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      
      const checkVolume = () => {
          if (!mountedRef.current || mediaRecorderRef.current?.state !== 'recording') return;

          analyser.getByteTimeDomainData(dataArray);
          let sum = 0;
          for(let i = 0; i < dataArray.length; i++) {
              let x = (dataArray[i] - 128) / 128.0;
              sum += x * x;
          }
          let rms = Math.sqrt(sum / dataArray.length);
          
          if (rms < 0.03) { 
              if (!silenceTimerRef.current) {
                  silenceTimerRef.current = setTimeout(() => {
                      console.log("Silence detected, stopping recording...");
                      stopRecording();
                  }, 2500);
              }
          } else {
              if (silenceTimerRef.current) {
                  clearTimeout(silenceTimerRef.current);
                  silenceTimerRef.current = null;
              }
          }
          animationFrameRef.current = requestAnimationFrame(checkVolume);
      };
      
      checkVolume();
  };

  const processAudio = async () => {
    if (isEnding) return;

    const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('session_id', sessionData.sessionId);
    formData.append('file', blob);

    try {
      const res = await fetch(`${API_URL}/process_audio`, { method: 'POST', body: formData });
      if (!res.ok) throw new Error("Audio processing failed");
      const data = await res.json();

      if (mountedRef.current && !isEnding) {
        if (data.user_text && data.user_text !== "[SILENCE]") {
          setUserTranscript(prev => [...prev, data.user_text]);
        }
        setText(data.ai_text);
        playAudio(data.audio_url, data.finished);
      }
    } catch (e) {
      console.error("Audio processing error:", e);
      showToast("Error processing audio. Retrying...", "error");
      if (mountedRef.current && !isEnding) setStatus('listening');
    }
  };

  const startRecording = async () => {
    if (isEnding) return;
    
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      mediaRecorderRef.current = new MediaRecorder(stream);
      chunksRef.current = [];
      mediaRecorderRef.current.ondataavailable = e => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mediaRecorderRef.current.onstop = () => {
           stream.getTracks().forEach(track => track.stop()); 
           processAudio();
      };

      audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)();
      analyserRef.current = audioCtxRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      const source = audioCtxRef.current.createMediaStreamSource(stream);
      source.connect(analyserRef.current);

      mediaRecorderRef.current.start();
      
      maxTimeRef.current = setTimeout(() => {
          console.log("Max recording time reached.");
          stopRecording();
      }, 60000);

      if (mountedRef.current) setStatus('listening');
      detectSilence(analyserRef.current);
      
    } catch (err) {
      console.error("Mic error", err);
      if (!isEnding) showToast("Microphone access denied or failed.", "error");
    }
  };

  const playAudio = async (url, isFinal = false) => {
    if (isEnding) return;

    if (!url || !audioRef.current) {
      if (!isFinal) startRecording();
      return;
    }
    
    try {
      if (mountedRef.current) setStatus('speaking');
      audioRef.current.src = url;
      audioRef.current.onended = () => {
        if (isEnding) return;
        if (isFinal) {
          onEndSession();
        } else {
          startRecording();
        }
      };
      await audioRef.current.play();
    } catch (err) {
      if (err.name === 'AbortError') {
          console.log("Audio play aborted (benign).");
      } else {
          console.error("Audio play error:", err.name);
          showToast("Audio playback error. Skipping...", "error");
          if (!isFinal && !isEnding) startRecording();
      }
    }
  };

  useEffect(() => {
    if (sessionData.initialAudio) {
        playAudio(sessionData.initialAudio);
    } else {
        startRecording();
    }
    
    return () => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current.src = "";
        }
    };
  }, []);

  return (
    <div className="voice-container">
      <div className="avatar-wrapper">
        <div className={`avatar-circle state-${status}`}>
            <span style={{position:'relative', zIndex:2}}>🤖</span>
            <div className={`avatar-circle state-${status}`} style={{position:'absolute', border:'none'}} />
        </div>
        <div className={`avatar-glow state-${status}`}></div>
      </div>

      <div className="status-indicator" style={{
        color: status === 'speaking' ? 'var(--primary)' : status === 'listening' ? 'var(--success)' : 'var(--warning)',
        borderColor: status === 'speaking' ? 'var(--primary)' : status === 'listening' ? 'var(--success)' : 'var(--warning)'
      }}>
        <div className="status-dot"></div>
        <span>{status === 'speaking' ? 'Interviewer Speaking' : status === 'listening' ? 'Listening...' : 'Thinking...'}</span>
      </div>

      <div className="text-display">
        {text}
      </div>

      {status === 'listening' && (
        <button onClick={stopRecording} className="manual-stop-btn">
          Tap if done speaking (Manual Override)
        </button>
      )}

      {userTranscript.length > 0 && (
        <div className="live-transcript">
          {userTranscript.map((t, i) => (
            <div key={i} style={{marginBottom: '8px'}}>
              <span style={{color: 'var(--primary)', fontWeight: 'bold'}}>You: </span>
              {t}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}