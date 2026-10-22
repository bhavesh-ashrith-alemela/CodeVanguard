'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Search, ChevronDown, Check, Lock, Globe, Plus } from 'lucide-react';
import { Repository } from '@/lib/api';
import { ActiveTab } from './Tabs';

interface RepoSwitcherProps {
  currentRepo?: Repository | null;
  repositories: Repository[];
  currentTab?: ActiveTab;
  className?: string;
}

export function RepoSwitcher({
  currentRepo,
  repositories = [],
  currentTab = 'overview',
  className = ''
}: RepoSwitcherProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [open]);

  const filtered = repositories.filter(r =>
    r.full_name.toLowerCase().includes(query.toLowerCase().trim())
  );

  const handleSelect = (repo: Repository) => {
    setOpen(false);
    setQuery('');
    if (currentTab === 'settings') {
      router.push(`/repos/${repo.id}/settings`);
    } else {
      router.push(`/repos/${repo.id}`);
    }
  };

  const displayName = currentRepo ? currentRepo.full_name : 'Select repository';

  return (
    <div className={`relative inline-block ${className}`} ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-2 px-4 py-2 border-2 border-[#14141A] rounded-full bg-white text-[#14141A] font-bold font-sans text-sm hover:bg-[#F5F4EE] cursor-pointer transition-colors select-none"
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <span className="truncate max-w-[200px] sm:max-w-[260px]">{displayName}</span>
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute left-0 mt-2 z-50 w-72 sm:w-80 border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] p-3 flex flex-col gap-2">
          {/* Search Input */}
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#55555F]" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter repositories..."
              autoFocus
              className="w-full pl-9 pr-3 py-1.5 border-2 border-[#14141A] rounded-full font-mono text-xs focus:outline-none focus:ring-2 focus:ring-[#D6F25B]"
            />
          </div>

          {/* Repo List */}
          <div className="max-h-60 overflow-y-auto flex flex-col gap-1 py-1 divide-y divide-[#E2E0D6]">
            {filtered.length === 0 ? (
              <p className="font-mono text-xs text-[#55555F] text-center py-4">
                No matching repositories found.
              </p>
            ) : (
              filtered.map((repo) => {
                const isSelected = currentRepo?.id === repo.id;
                return (
                  <button
                    key={repo.id}
                    onClick={() => handleSelect(repo)}
                    className={`flex items-center justify-between gap-2 p-2 rounded-lg text-left text-xs font-mono font-medium hover:bg-[#F5F4EE] transition-colors cursor-pointer ${
                      isSelected ? 'bg-[#F6FBDD] font-bold text-[#14141A]' : 'text-[#3C3C46]'
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      {repo.is_private ? (
                        <Lock className="w-3.5 h-3.5 flex-shrink-0 text-[#14141A]" />
                      ) : (
                        <Globe className="w-3.5 h-3.5 flex-shrink-0 text-[#55555F]" />
                      )}
                      <span className="truncate">{repo.full_name}</span>
                    </div>
                    {isSelected && <Check className="w-4 h-4 flex-shrink-0 text-[#14141A]" />}
                  </button>
                );
              })
            )}
          </div>

          <div className="pt-2 border-t border-[#E2E0D6]">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                router.push('/dashboard?connect=true');
              }}
              className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg border-2 border-[#14141A] bg-[#D6F25B] text-[#14141A] font-mono text-xs font-bold hover:bg-[#c5e44a] transition-colors cursor-pointer shadow-[2px_2px_0_#14141A] active:translate-x-0.5 active:translate-y-0.5 active:shadow-none"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Connect Repository</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
