import React from 'react';

interface SkeletonProps {
  className?: string;
  style?: React.CSSProperties;
}

export function Skeleton({ className = '', style }: SkeletonProps) {
  return (
    <div
      style={style}
      className={`animate-pulse bg-[#E2E0D6] border-2 border-[#14141A] rounded-lg ${className}`}
    />
  );
}

export function SkeletonStatusCard() {
  return (
    <div className="border-2 border-[#14141A] rounded-[18px] bg-white p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-4 animate-pulse">
      <div className="flex justify-between items-center gap-4 flex-wrap">
        <div className="flex flex-col gap-2">
          <div className="w-28 h-6 bg-[#E2E0D6] border border-[#14141A] rounded-lg" />
          <div className="w-64 h-8 bg-[#E2E0D6] border border-[#14141A] rounded-lg" />
        </div>
        <div className="w-36 h-4 bg-[#E2E0D6] rounded" />
      </div>

      {/* Bar skeleton */}
      <div className="h-5 w-full bg-[#E2E0D6] border-2 border-[#14141A] rounded-full" />

      {/* Breakdown skeleton */}
      <div className="flex gap-6">
        <div className="w-20 h-5 bg-[#E2E0D6] rounded" />
        <div className="w-20 h-5 bg-[#E2E0D6] rounded" />
        <div className="w-20 h-5 bg-[#E2E0D6] rounded" />
        <div className="w-20 h-5 bg-[#E2E0D6] rounded" />
      </div>
    </div>
  );
}

export function SkeletonCard() {
  return (
    <div className="border-2 border-[#14141A] rounded-[18px] bg-white p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-3 animate-pulse">
      <div className="w-48 h-6 bg-[#E2E0D6] border border-[#14141A] rounded-lg" />
      <div className="w-full h-4 bg-[#E2E0D6] rounded" />
      <div className="w-3/4 h-4 bg-[#E2E0D6] rounded" />
    </div>
  );
}
