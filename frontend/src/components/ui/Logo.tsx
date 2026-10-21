import React from 'react';
import Link from 'next/link';

interface LogoProps {
  size?: number;
  showWordmark?: boolean;
  href?: string;
  className?: string;
}

export function Logo({
  size = 34,
  showWordmark = true,
  href,
  className = ''
}: LogoProps) {
  const content = (
    <div className={`inline-flex items-center gap-3 select-none ${className}`}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 52 52"
        role="img"
        aria-label="CodeVanguard"
        className="flex-shrink-0"
      >
        <rect x="8" y="8" width="44" height="44" rx="12" fill="#B8A2FF" stroke="#14141A" strokeWidth="2" />
        <rect x="2" y="2" width="44" height="44" rx="12" fill="#14141A" />
        <path
          d="M14 17L24 34L34 17"
          fill="none"
          stroke="#D6F25B"
          strokeWidth="6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="24" cy="14" r="3.8" fill="#FF6B3D" />
      </svg>
      {showWordmark && (
        <span className="font-sans font-bold text-xl md:text-2xl text-[#14141A] tracking-tight leading-none">
          <span className="font-medium">Code</span>Vanguard
        </span>
      )}
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="inline-flex items-center hover:opacity-95 transition-opacity">
        {content}
      </Link>
    );
  }

  return content;
}
