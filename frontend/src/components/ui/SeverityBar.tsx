import React from 'react';

interface SeverityBarProps {
  critical: number;
  high: number;
  medium: number;
  low: number;
  className?: string;
}

export function SeverityBar({
  critical = 0,
  high = 0,
  medium = 0,
  low = 0,
  className = ''
}: SeverityBarProps) {
  const total = critical + high + medium + low;

  if (total === 0) {
    return (
      <div
        role="img"
        aria-label="No vulnerabilities detected"
        className={`flex h-5 border-2 border-[#14141A] rounded-full overflow-hidden bg-[#D6F25B] items-center justify-center font-mono text-[11px] font-bold text-[#14141A] select-none ${className}`}
      >
        CLEAN · 0 ISSUES
      </div>
    );
  }

  const ariaLabel = `Severity split: ${critical} critical, ${high} high, ${medium} medium, ${low} low`;

  // First non-zero index should not have border-left
  const nonZeroSegments = [
    { count: critical, color: '#FF6B3D', label: 'Critical' },
    { count: high, color: '#FFC93C', label: 'High' },
    { count: medium, color: '#B8A2FF', label: 'Medium' },
    { count: low, color: '#D6F25B', label: 'Low' }
  ].filter(s => s.count > 0);

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      className={`flex h-5 border-2 border-[#14141A] rounded-full overflow-hidden w-full select-none ${className}`}
    >
      {nonZeroSegments.map((segment, index) => (
        <div
          key={segment.label}
          style={{
            flex: segment.count,
            backgroundColor: segment.color,
            borderLeft: index > 0 ? '2px solid #14141A' : 'none'
          }}
          title={`${segment.count} ${segment.label}`}
        />
      ))}
    </div>
  );
}
