import React, { useState, useCallback } from 'react';
import { X } from 'lucide-react';
import { ToastContext } from './ToastContextHelpers';

export const ToastProvider = ({ children }) => {
  const [toasts, setToasts] = useState([]);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback((message, type = 'info') => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);

    setTimeout(() => {
      removeToast(id);
    }, 4000);
  }, [removeToast]);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div id="toast-container" style={{
        position: 'fixed', bottom: '20px', right: '20px', display: 'flex', flexDirection: 'column', gap: '10px', zIndex: 1000, maxWidth: '500px'
      }}>
        {toasts.map((toast) => (
          <div 
            key={toast.id} 
            className={`toast show ${toast.type === 'error' ? 'error' : 'success'}`}
            style={{ 
                minWidth: '250px', padding: '12px 20px', borderRadius: '8px', 
                background: 'rgba(30, 30, 40, 0.95)', backdropFilter: 'blur(10px)', 
                color: '#fff', fontSize: '0.9rem', boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
                borderLeft: `4px solid ${toast.type === 'error' ? '#ff5555' : '#00d9a5'}`,
                display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px'
            }}
          >
            <span>{toast.message}</span>
            <button 
              onClick={() => removeToast(toast.id)}
              style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0, display: 'flex' }}
            >
              <X size={16} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
};