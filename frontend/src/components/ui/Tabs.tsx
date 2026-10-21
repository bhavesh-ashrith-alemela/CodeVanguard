'use client';

import React from 'react';
import Link from 'next/link';

export type ActiveTab = 'overview' | 'pulls' | 'findings' | 'settings';

interface TabsProps {
  repoId: string;
  activeTab: ActiveTab;
  className?: string;
}

export function Tabs({ repoId, activeTab, className = '' }: TabsProps) {
  const tabs: { id: ActiveTab; label: string; href: string }[] = [
    { id: 'overview', label: 'Overview', href: `/repos/${repoId}` },
    { id: 'pulls', label: 'Pull requests', href: `/repos/${repoId}/pulls` },
    { id: 'findings', label: 'Findings', href: `/repos/${repoId}/findings` },
    { id: 'settings', label: 'Settings', href: `/repos/${repoId}/settings` }
  ];

  return (
    <nav
      aria-label="Repository navigation"
      className={`inline-flex items-center gap-1 p-1 border-2 border-[#14141A] rounded-full bg-white select-none ${className}`}
    >
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <Link
            key={tab.id}
            href={tab.href}
            className={`px-4 py-1.5 rounded-full font-sans text-sm font-bold tracking-tight transition-all text-center whitespace-nowrap ${
              isActive
                ? 'bg-[#14141A] text-[#F5F4EE]'
                : 'text-[#14141A] hover:bg-[#F5F4EE]'
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
