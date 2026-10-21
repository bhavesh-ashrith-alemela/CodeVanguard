import React from 'react';

export type ChipVariant = 
  | 'critical'
  | 'high'
  | 'medium'
  | 'low'
  | 'attention'
  | 'safe'
  | 'block'
  | 'review'
  | 'running'
  | 'completed'
  | 'failed'
  | 'verified'
  | 'generating'
  | 'rejected'
  | 'pr_opened'
  | 'neutral';

interface ChipProps {
  label: string;
  variant?: ChipVariant;
  className?: string;
}

const chipVariantStyles: Record<ChipVariant, string> = {
  critical: 'bg-[#FF6B3D] text-white',
  high: 'bg-[#FFC93C] text-[#14141A]',
  medium: 'bg-[#B8A2FF] text-[#14141A]',
  low: 'bg-[#D6F25B] text-[#14141A]',
  attention: 'bg-[#FFC93C] text-[#14141A]',
  safe: 'bg-[#D6F25B] text-[#14141A]',
  block: 'bg-[#FF6B3D] text-white',
  review: 'bg-[#FFC93C] text-[#14141A]',
  running: 'bg-[#FFC93C] text-[#14141A]',
  completed: 'bg-[#D6F25B] text-[#14141A]',
  failed: 'bg-[#FF6B3D] text-white',
  verified: 'bg-[#D6F25B] text-[#14141A]',
  generating: 'bg-[#FFC93C] text-[#14141A]',
  rejected: 'bg-[#FF6B3D] text-white',
  pr_opened: 'bg-[#B8A2FF] text-[#14141A]',
  neutral: 'bg-white text-[#14141A]'
};

export function Chip({ label, variant = 'neutral', className = '' }: ChipProps) {
  return (
    <span
      className={`inline-block font-mono font-bold text-xs px-2 py-0.5 border-2 border-[#14141A] rounded-lg tracking-wider whitespace-nowrap select-none ${chipVariantStyles[variant]} ${className}`}
    >
      {label}
    </span>
  );
}
