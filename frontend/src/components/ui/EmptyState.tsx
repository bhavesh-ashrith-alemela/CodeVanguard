import React from 'react';
import { Button } from './Button';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
  external?: boolean;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  actionHref,
  onAction,
  external = false,
  className = ''
}: EmptyStateProps) {
  return (
    <div
      className={`border-2 border-[#14141A] rounded-[18px] bg-white p-10 md:p-14 text-center shadow-[5px_5px_0_#14141A] flex flex-col items-center justify-center gap-4 ${className}`}
    >
      {icon && (
        <div className="w-14 h-14 rounded-[14px] bg-[#F5F4EE] border-2 border-[#14141A] flex items-center justify-center text-[#14141A] mb-1">
          {icon}
        </div>
      )}
      <div className="max-w-md flex flex-col gap-1.5">
        <h3 className="text-2xl font-bold font-sans text-[#14141A] tracking-tight m-0">
          {title}
        </h3>
        <p className="text-sm font-sans text-[#55555F] leading-relaxed m-0">
          {description}
        </p>
      </div>

      {actionLabel && (
        <div className="pt-2">
          {actionHref ? (
            <Button
              variant="action"
              size="md"
              href={actionHref}
              external={external}
            >
              {actionLabel}
            </Button>
          ) : (
            <Button
              variant="action"
              size="md"
              onClick={onAction}
            >
              {actionLabel}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
