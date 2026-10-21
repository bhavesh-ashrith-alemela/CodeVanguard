import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from './Button';

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
  className = ''
}: ErrorStateProps) {
  return (
    <div
      className={`border-2 border-[#14141A] rounded-[18px] bg-white p-8 text-center shadow-[5px_5px_0_#14141A] flex flex-col items-center justify-center gap-4 ${className}`}
    >
      <div className="w-12 h-12 rounded-[14px] bg-[#FFD9CC] border-2 border-[#14141A] flex items-center justify-center text-[#FF6B3D]">
        <AlertTriangle className="w-6 h-6" />
      </div>
      <div className="max-w-md flex flex-col gap-1.5">
        <h3 className="text-xl font-bold font-sans text-[#14141A] m-0">
          {title}
        </h3>
        <p className="text-xs font-mono text-[#55555F] leading-relaxed m-0">
          {message}
        </p>
      </div>

      {onRetry && (
        <div className="pt-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={onRetry}
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Try again</span>
          </Button>
        </div>
      )}
    </div>
  );
}
