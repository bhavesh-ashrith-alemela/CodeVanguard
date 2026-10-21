'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { LogOut, User as UserIcon } from 'lucide-react';
import { Logo } from './Logo';
import { RepoSwitcher } from './RepoSwitcher';
import { Tabs, ActiveTab } from './Tabs';
import { Repository, User, fetchApi } from '@/lib/api';

interface HeaderProps {
  currentRepo?: Repository | null;
  repositories?: Repository[];
  activeTab?: ActiveTab;
  rightAction?: React.ReactNode;
  className?: string;
}

export function Header({
  currentRepo,
  repositories = [],
  activeTab,
  rightAction,
  className = ''
}: HeaderProps) {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<User | null>(null);

  useEffect(() => {
    let isMounted = true;
    async function loadUser() {
      try {
        const res = await fetchApi('/api/auth/me');
        if (res.ok) {
          const user = await res.json();
          if (isMounted) setCurrentUser(user);
        }
      } catch {
        // Ignored if unauthorized
      }
    }
    loadUser();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleLogout = async () => {
    try {
      await fetchApi('/api/auth/logout', { method: 'POST' });
    } catch {
      // Ignored
    }
    router.push('/login');
  };

  return (
    <header className={`flex items-center justify-between gap-4 flex-wrap pb-4 select-none ${className}`}>
      {/* Left Section: Logo + RepoSwitcher + Tabs */}
      <div className="flex items-center gap-3.5 flex-wrap">
        <Logo size={34} href={currentRepo ? `/repos/${currentRepo.id}` : '/dashboard'} />

        {currentRepo && (
          <>
            <RepoSwitcher
              currentRepo={currentRepo}
              repositories={repositories}
              currentTab={activeTab || 'overview'}
            />

            {activeTab && (
              <Tabs
                repoId={currentRepo.id}
                activeTab={activeTab}
              />
            )}
          </>
        )}
      </div>

      {/* Right Section: Action Button + User Menu */}
      <div className="flex items-center gap-3 flex-wrap">
        {rightAction}

        {currentUser && (
          <div className="flex items-center gap-2 bg-white border-2 border-[#14141A] rounded-full py-1 pl-1.5 pr-3 shadow-[2px_2px_0_#14141A]">
            {currentUser.avatar_url ? (
              <img
                src={currentUser.avatar_url}
                alt={currentUser.github_login || 'user avatar'}
                className="w-6 h-6 rounded-full border border-[#14141A]"
              />
            ) : (
              <UserIcon className="w-4 h-4 text-[#55555F]" />
            )}
            <span className="font-mono text-xs font-bold text-[#14141A] max-w-[120px] truncate">
              {currentUser.github_login || currentUser.username}
            </span>
            <button
              onClick={handleLogout}
              className="ml-1 text-[#55555F] hover:text-[#FF6B3D] transition-colors cursor-pointer"
              title="Sign out of CodeVanguard"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
