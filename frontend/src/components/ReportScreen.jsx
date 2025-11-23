import React from 'react';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler } from 'chart.js';
import { Line } from 'react-chartjs-2';
import { Download, RefreshCcw } from 'lucide-react';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

export default function ReportScreen({ data, onRestart }) {
  const isRawArray = Array.isArray(data);
  
  const transcript = isRawArray ? data : (data?.transcript_analysis || []);
  const summary = isRawArray ? "Report generated based on transcript analysis." : (data?.summary || "No summary available.");
  const strengths = isRawArray ? ["See detailed feedback below"] : (data?.strengths || []);
  const areas = isRawArray ? ["See detailed feedback below"] : (data?.areas_for_improvement || []);
  
  const commScore = isRawArray ? Math.round(transcript.reduce((acc, t) => acc + (t.clarity_score || 0), 0) / (transcript.length || 1)) : (data?.communication_rating || 0);
  const techScore = isRawArray ? Math.round(transcript.reduce((acc, t) => acc + (t.technical_accuracy_score || 0), 0) / (transcript.length || 1)) : (data?.technical_rating || 0);
  const cultScore = isRawArray ? Math.round(transcript.reduce((acc, t) => acc + (t.relevance_score || 0), 0) / (transcript.length || 1)) : (data?.culture_fit_rating || 0);

  const chartData = {
    labels: transcript.map((_, i) => `Q${i + 1}`),
    datasets: [{
      label: 'Performance Score',
      data: transcript.map(t => t.overall_score),
      borderColor: '#6C63FF',
      backgroundColor: 'rgba(108, 99, 255, 0.1)',
      tension: 0.4,
      fill: true 
    }]
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: { beginAtZero: true, max: 10, grid: { color: 'rgba(255, 255, 255, 0.1)' } },
      x: { grid: { display: false } }
    },
    plugins: { legend: { display: false } }
  };

  return (
    <div className="glass-card">
      <div className="report-header">
        <h1>Interview Report</h1>
        <button onClick={onRestart} className="btn btn-secondary">
          <RefreshCcw size={16} /> New Session
        </button>
      </div>

      <div className="summary-card">
        <h4 className="summary-title">Executive Summary</h4>
        <p style={{lineHeight: 1.6, color: '#ddd'}}>{summary}</p>
        
        <div className="scores-row">
          <Badge score={commScore} label="Communication" />
          <Badge score={techScore} label="Technical" />
          <Badge score={cultScore} label="Culture Fit" />
        </div>

        <div className="grid-2">
          <div className="feedback-box strengths">
            <h5 style={{color: '#00d9a5', fontWeight: 'bold'}}>✅ Strengths</h5>
            <ul className="feedback-list">
              {strengths.length > 0 ? strengths.map((s, i) => <li key={i}>{s}</li>) : <li>No specific strengths listed.</li>}
            </ul>
          </div>
          <div className="feedback-box improvements">
            <h5 style={{color: '#ff5555', fontWeight: 'bold'}}>⚠️ Improvements</h5>
            <ul className="feedback-list">
              {areas.length > 0 ? areas.map((s, i) => <li key={i}>{s}</li>) : <li>No specific improvements listed.</li>}
            </ul>
          </div>
        </div>
      </div>

      <div className="chart-wrapper">
        <Line data={chartData} options={chartOptions} />
      </div>

      <div style={{overflowX: 'auto'}}>
        <table className="report-table">
          <thead>
            <tr>
              <th style={{width: '35%'}}>Question</th>
              <th>Feedback</th>
              <th style={{textAlign: 'right'}}>Score</th>
            </tr>
          </thead>
          <tbody>
            {transcript.length > 0 ? transcript.map((t, i) => (
              <tr key={i}>
                <td>{t.question}</td>
                <td>
                  <p style={{fontSize: '0.9rem', color: '#aaa', marginBottom: '5px'}}>{t.feedback}</p>
                  <div>
                    <span className="mini-pill">Rel: {t.relevance_score}</span>
                    <span className="mini-pill">Clar: {t.clarity_score}</span>
                    <span className="mini-pill">Tech: {t.technical_accuracy_score}</span>
                  </div>
                </td>
                <td style={{textAlign: 'right', fontWeight: 'bold', fontSize: '1.2rem', color: t.overall_score >= 7 ? 'var(--success)' : 'var(--error)'}}>
                  {t.overall_score}
                </td>
              </tr>
            )) : (
                <tr><td colSpan="3" style={{textAlign: 'center', padding: '20px'}}>No transcript data available.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={{marginTop: '2rem', textAlign: 'right'}}>
        <button onClick={() => window.print()} className="btn btn-primary" style={{width: 'auto', display: 'inline-flex'}}>
          <Download size={18} /> Download PDF
        </button>
      </div>
    </div>
  );
}

const Badge = ({ score, label }) => (
  <div className="score-badge">
    <div className="score-dot" style={{backgroundColor: score >= 7 ? 'var(--success)' : 'var(--warning)'}}></div>
    <span style={{fontWeight: 'bold', color: 'white'}}>{score}/10</span>
    <span style={{fontSize: '0.75rem', color: '#aaa', textTransform: 'uppercase'}}>{label}</span>
  </div>
);