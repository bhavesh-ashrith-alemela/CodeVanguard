'use client';

import React, { createContext, useContext, useState, useCallback } from 'react';
import { Info, CheckCircle, AlertTriangle } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'info';

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextType {
  showToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback((message: string, type: ToastType = 'info') => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);

    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      
      {/* Toast container in bottom-right corner */}
      <div className="fixed bottom-4 right-4 z-50 pointer-events-none flex flex-col gap-2 max-w-sm w-full px-4">
        {toasts.map((toast) => {
          let alertClass = 'alert-info';
          let Icon = Info;
          
          if (toast.type === 'success') {
            alertClass = 'alert-success bg-green-50 text-green-800 border-green-400';
            Icon = CheckCircle;
          } else if (toast.type === 'error') {
            alertClass = 'alert-error bg-red-50 text-red-800 border-red-400';
            Icon = AlertTriangle;
          } else {
            alertClass = 'alert-info bg-sky-50 text-sky-800 border-sky-400';
            Icon = Info;
          }

          return (
            <div
              key={toast.id}
              className={`alert shadow-lg pointer-events-auto border-2 border-slate-900 rounded-xl p-4 flex items-center gap-3 animate-slide-up bg-white`}
              style={{
                boxShadow: '3px 3px 0px #0f172a',
                transition: 'opacity 0.5s ease',
              }}
            >
              <Icon className="w-5 h-5 flex-shrink-0" />
              <span className="text-xs font-bold font-sans">{toast.message}</span>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
