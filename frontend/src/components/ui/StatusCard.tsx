import React from 'react';
import { Chip } from './Chip';
import { SeverityBar } from './SeverityBar';

interface StatusCardProps {
  status: 'pending' | 'running' | 'completed' | 'failed' | 'not_scanned';
  branch?: string;
  timestamp?: string;
  critical?: number;
  high?: number;
  medium?: number;
  low?: number;
  totalIssues?: number;
  className?: string;
}

export function StatusCard({
  status,
  branch = 'main',
  timestamp,
  critical = 0,
  high = 0,
  medium = 0,
  low = 0,
  totalIssues = 0,
  className = ''
}: StatusCardProps) {
  const isPendingOrRunning = status === 'pending' || status === 'running';
  const isFailed = status === 'failed';
  const isClean = status === 'completed' && totalIssues === 0;
  const hasIssues = status === 'completed' && totalIssues > 0;

  // Format time ago or date
  let timeDisplay = '';
  if (timestamp) {
    try {
      const date = new Date(timestamp);
      const diffMs = Date.now() - date.getTime();
      const diffMinutes = Math.floor(diffMs / 60000);
      if (diffMinutes < 1) {
        timeDisplay = 'scanned just now';
      } else if (diffMinutes < 60) {
        timeDisplay = `scanned ${diffMinutes} min ago`;
      } else {
        const diffHours = Math.floor(diffMinutes / 60);
        if (diffHours < 24) {
          timeDisplay = `scanned ${diffHours}h ago`;
        } else {
          timeDisplay = `scanned on ${date.toLocaleDateString()}`;
        }
      }
    } catch {
      timeDisplay = `scanned ${timestamp}`;
    }
  }

  const metaString = [branch, timeDisplay].filter(Boolean).join(' · ');

  return (
    <section
      className={`border-2 border-[#14141A] rounded-[18px] bg-white p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-4.5 ${className}`}
    >
      <div className="flex justify-between items-center gap-3 flex-wrap">
        <div className="flex flex-col gap-2">
          {hasIssues && <Chip label="NEEDS ATTENTION" variant="attention" className="self-start" />}
          {isClean && <Chip label="CLEAN CODE" variant="safe" className="self-start" />}
          {isPendingOrRunning && <Chip label="SCANNING NOW" variant="running" className="self-start" />}
          {isFailed && <Chip label="SCAN FAILED" variant="failed" className="self-start" />}
          {status === 'not_scanned' && <Chip label="NOT SCANNED" variant="neutral" className="self-start" />}

          <h2 className="text-2xl md:text-3xl font-bold font-sans text-[#14141A] tracking-tight m-0">
            {hasIssues && `${totalIssues} issue${totalIssues === 1 ? '' : 's'} to fix first`}
            {isClean && 'Zero vulnerabilities detected'}
            {isPendingOrRunning && 'Analyzing code and dependencies...'}
            {isFailed && 'Scan encountered an error'}
            {status === 'not_scanned' && 'Ready for first scan'}
          </h2>
        </div>

        {metaString && (
          <span className="font-mono text-xs text-[#55555F]">
            {metaString}
          </span>
        )}
      </div>

      {/* Severity Split Bar */}
      <SeverityBar
        critical={critical}
        high={high}
        medium={medium}
        low={low}
      />

      {/* Severity Breakdown Counts */}
      <div className="flex gap-4 sm:gap-7 flex-wrap font-sans text-sm md:text-[15px] text-[#14141A]">
        <span><b>{critical}</b> Critical</span>
        <span><b>{high}</b> High</span>
        <span><b>{medium}</b> Medium</span>
        <span><b>{low}</b> Low</span>
      </div>
    </section>
  );
}
