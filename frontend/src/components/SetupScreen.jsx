import React, { useState } from 'react';
import { Play, Mic, MessageSquare } from 'lucide-react';
import { API_URL } from '../config';
import { useToast } from '../context/ToastContext';

export default function SetupScreen({ onStart }) {
  const [formData, setFormData] = useState({
    name: '',
    role: '',
    duration: 10,
    mode: 'voice'
  });
  const [resume, setResume] = useState(null);
  const [loading, setLoading] = useState(false);
  const { showToast } = useToast();

  const handleSubmit = async (e) => {
    e.preventDefault();

    const dur = parseInt(formData.duration);
    if (isNaN(dur) || dur < 3 || dur > 45) {
      showToast("Duration must be between 3 and 45 minutes.", "error");
      return;
    }

    if (!resume) {
      showToast('Please upload your resume (PDF) to continue.', "error");
      return;
    }

    setLoading(true);
    const body = new FormData();
    body.append('name', formData.name);
    body.append('role', formData.role);
    body.append('duration', formData.duration);
    body.append('mode', formData.mode); 
    body.append('resume', resume);

    try {
      const res = await fetch(`${API_URL}/start_interview`, { method: 'POST', body });
      
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Server error");
      }
      
      const data = await res.json();
      showToast("Session started successfully", "success");
      
      onStart({
        sessionId: data.session_id,
        initialText: data.text,
        initialAudio: data.audio_url,
        mode: formData.mode,
        durationMinutes: formData.duration
      });
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card relative">
      <div className="header-container">
        <div className="logo-box">
          <Play size={24} color="white" fill="white" />
        </div>
        <div>
          <h1 className="title-text">AI Interview Pro</h1>
          <p style={{color: 'var(--muted)', fontSize: '0.9rem'}}>Agentic Interviewer</p>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="label">Your Name *</label>
          <input 
            type="text" required
            className="input-field"
            placeholder="Enter your full name"
            value={formData.name}
            onChange={e => setFormData({...formData, name: e.target.value})}
          />
        </div>

        <div className="form-group">
          <label className="label">Target Job Role *</label>
          <input 
            type="text" required
            className="input-field"
            placeholder="e.g. Software Engineer"
            value={formData.role}
            onChange={e => setFormData({...formData, role: e.target.value})}
          />
        </div>

        <div className="form-group">
          <label className="label">Duration (Minutes) *</label>
          <input 
            type="number" min="3" max="45" required
            className="input-field"
            value={formData.duration}
            onChange={e => setFormData({...formData, duration: e.target.value})}
          />
          <p className="text-xs text-gray-500 mt-1" style={{fontSize:'0.75rem', color:'#666'}}>Min: 3, Max: 45 mins</p>
        </div>

        <div className="form-group">
          <label className="label">Interview Mode</label>
          <div className="radio-group">
            <label className={`radio-label ${formData.mode === 'voice' ? 'selected' : ''}`}>
              <input type="radio" name="mode" className="hidden" 
                checked={formData.mode === 'voice'} 
                onChange={() => setFormData({...formData, mode: 'voice'})} 
              />
              <div className="radio-icon">
                <Mic size={20} />
              </div>
              <div>
                <div style={{fontWeight: 600}}>Voice</div>
                <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>Real-time speech</div>
              </div>
            </label>

            <label className={`radio-label ${formData.mode === 'chat' ? 'selected' : ''}`}>
              <input type="radio" name="mode" className="hidden" 
                checked={formData.mode === 'chat'} 
                onChange={() => setFormData({...formData, mode: 'chat'})} 
              />
              <div className="radio-icon">
                <MessageSquare size={20} />
              </div>
              <div>
                <div style={{fontWeight: 600}}>Chat</div>
                <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>Text messaging</div>
              </div>
            </label>
          </div>
        </div>

        <div className="form-group">
          <label className="label">Resume (PDF) *</label>
          <input 
            type="file" accept=".pdf" required
            onChange={e => setResume(e.target.files[0])}
            className="file-input"
          />
        </div>

        <button disabled={loading} className="btn btn-primary">
          {loading ? <div className="spinner" /> : <Play size={18} fill="currentColor" />}
          <span>{loading ? 'Starting...' : 'Start Interview'}</span>
        </button>
      </form>
    </div>
  );
}