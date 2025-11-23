import React, { useState } from 'react';
import SetupScreen from './components/SetupScreen';
import LiveSession from './components/LiveSession';
import ReportScreen from './components/ReportScreen';
import { ToastProvider } from './context/ToastContext';

function AppContent() {
  const [currentScreen, setCurrentScreen] = useState('setup'); 
  const [sessionData, setSessionData] = useState(null);
  const [reportData, setReportData] = useState(null);
  const [interviewMode, setInterviewMode] = useState('voice');

  const startSession = (data) => {
    setSessionData(data);
    setInterviewMode(data.mode);
    setCurrentScreen('session');
  };

  const endSession = (data) => {
    setReportData(data);
    setCurrentScreen('report');
  };

  const resetSession = () => {
    setSessionData(null);
    setReportData(null);
    setCurrentScreen('setup');
  };

  return (
    <div className="app-container">
      <main className="main-content">
        {currentScreen === 'setup' && (
          <SetupScreen onStart={startSession} />
        )}
        
        {currentScreen === 'session' && sessionData && (
          <LiveSession 
            sessionData={sessionData} 
            interviewMode={interviewMode}
            onEnd={endSession} 
          />
        )}

        {currentScreen === 'report' && reportData && (
          <ReportScreen 
            data={reportData} 
            onRestart={resetSession} 
          />
        )}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
}