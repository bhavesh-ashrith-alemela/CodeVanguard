'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { 
  Shield, PlusCircle, Code, History, Lock, LogOut, Menu, 
  FolderGit2, User as UserIcon
} from 'lucide-react';
import { fetchApi, User } from '@/lib/api';
import { useToast } from './ToastProvider';

function GithubIcon({ className = "w-3.5 h-3.5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { showToast } = useToast();
  
  const [adminUsername, setAdminUsername] = useState<string | null>(null);
  const [githubUser, setGithubUser] = useState<User | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState<boolean>(false);

  const checkAuth = async () => {
    if (typeof window !== 'undefined') {
      const username = localStorage.getItem('admin_username');
      setAdminUsername(username);

      // Check GitHub App OAuth session via /api/auth/me
      try {
        const res = await fetchApi('/api/auth/me');
        if (res.ok) {
          const user = await res.json();
          setGithubUser(user);
        } else {
          setGithubUser(null);
        }
      } catch {
        setGithubUser(null);
      }
    }
  };

  useEffect(() => {
    checkAuth();
    
    // Listen to custom auth events
    window.addEventListener('auth-change', checkAuth);
    return () => {
      window.removeEventListener('auth-change', checkAuth);
    };
  }, []);

  const handleAdminLogout = (e: React.MouseEvent) => {
    e.preventDefault();
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_username');
    setAdminUsername(null);
    showToast('Logged out of admin portal.', 'info');
    window.dispatchEvent(new Event('auth-change'));
    router.push('/');
  };

  const handleGithubLogout = async (e: React.MouseEvent) => {
    e.preventDefault();
    try {
      await fetchApi('/api/auth/logout', { method: 'POST' });
    } catch {
      // Ignore network errors on logout
    }
    setGithubUser(null);
    showToast('Signed out of GitHub.', 'info');
    window.dispatchEvent(new Event('auth-change'));
    router.push('/');
  };

  const isScanActive = pathname === '/scan';
  const isDashboardActive = pathname.startsWith('/dashboard') || pathname.startsWith('/repos');
  const isExamplesActive = pathname === '/examples';
  const isHistoryActive = pathname === '/history';

  return (
    <div className="sticky top-0 z-50 w-full bg-[#F5F4EE] border-b-2 border-[#14141A]">
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between py-3">
        {/* Brand with mark from Logo.dc.html */}
        <div className="flex-1">
          <Link href="/" className="inline-flex items-center gap-2.5 font-black text-xl tracking-tight text-[#14141A] hover:opacity-90">
            <svg width="32" height="32" viewBox="0 0 52 52" role="img" aria-label="CodeVanguard">
              <rect x="2" y="2" width="44" height="44" rx="12" fill="#14141A" />
              <path d="M14 17L24 34L34 17" fill="none" stroke="#D6F25B" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="24" cy="14" r="3.8" fill="#FF6B3D" />
            </svg>
            <span className="tracking-tight text-xl font-bold">
              <span className="font-medium">Code</span>Vanguard
            </span>
          </Link>
        </div>
        
        {/* Desktop Menu */}
        <div className="flex-none gap-3 items-center hidden md:flex">
          <nav aria-label="Main" className="flex items-center gap-1 p-1 border-2 border-[#14141A] rounded-full bg-white shadow-[2px_2px_0_#14141A]">
            <Link 
              href="/scan" 
              className={`py-1.5 px-4 rounded-full text-xs font-bold transition-all ${
                isScanActive ? 'bg-[#14141A] text-[#F5F4EE]' : 'text-[#14141A] hover:bg-[#F5F4EE]'
              }`}
            >
              Scan
            </Link>

            {githubUser && (
              <Link 
                href="/dashboard" 
                className={`py-1.5 px-4 rounded-full text-xs font-bold transition-all ${
                  isDashboardActive ? 'bg-[#14141A] text-[#F5F4EE]' : 'text-[#14141A] hover:bg-[#F5F4EE]'
                }`}
              >
                Repositories
              </Link>
            )}

            <Link 
              href="/examples" 
              className={`py-1.5 px-4 rounded-full text-xs font-bold transition-all ${
                isExamplesActive ? 'bg-[#14141A] text-[#F5F4EE]' : 'text-[#14141A] hover:bg-[#F5F4EE]'
              }`}
            >
              Examples
            </Link>

            <Link 
              href="/history" 
              className={`py-1.5 px-4 rounded-full text-xs font-bold transition-all ${
                isHistoryActive ? 'bg-[#14141A] text-[#F5F4EE]' : 'text-[#14141A] hover:bg-[#F5F4EE]'
              }`}
            >
              History
            </Link>

            <Link 
              href="/privacy" 
              className={`py-1.5 px-4 rounded-full text-xs font-bold transition-all ${
                pathname === '/privacy' ? 'bg-[#14141A] text-[#F5F4EE]' : 'text-[#14141A] hover:bg-[#F5F4EE]'
              }`}
            >
              Privacy
            </Link>

            <Link 
              href="/status" 
              className={`py-1.5 px-4 rounded-full text-xs font-bold transition-all ${
                pathname === '/status' ? 'bg-[#14141A] text-[#F5F4EE]' : 'text-[#14141A] hover:bg-[#F5F4EE]'
              }`}
            >
              Status
            </Link>
          </nav>

          {/* User / Auth Pill */}
          <div className="flex items-center gap-2 pl-2">
            {githubUser ? (
              <div className="flex items-center gap-2 bg-white border-2 border-[#14141A] rounded-full py-1 pl-1.5 pr-3 shadow-[2px_2px_0_#14141A]">
                {githubUser.avatar_url ? (
                  <img 
                    src={githubUser.avatar_url} 
                    alt={githubUser.github_login || 'avatar'} 
                    className="w-6 h-6 rounded-full border border-[#14141A]" 
                  />
                ) : (
                  <UserIcon className="w-5 h-5 text-[#55555F]" />
                )}
                <span className="font-mono text-xs font-bold text-[#14141A]">
                  {githubUser.github_login || githubUser.username}
                </span>
                <button
                  onClick={handleGithubLogout}
                  className="ml-1 text-[#55555F] hover:text-[#FF6B3D] cursor-pointer"
                  title="Sign out of GitHub"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <Link
                href="/login"
                className="py-1.5 px-4 border-2 border-[#14141A] rounded-full bg-white text-[#14141A] font-bold text-xs shadow-[2px_2px_0_#14141A] hover:shadow-[1px_1px_0_#14141A] hover:translate-x-[1px] hover:translate-y-[1px] transition-all flex items-center gap-1.5"
              >
                <GithubIcon className="w-3.5 h-3.5" />
                <span>Sign in</span>
              </Link>
            )}

            {adminUsername && (
              <div className="flex items-center gap-1.5 bg-[#FFD9CC] border-2 border-[#14141A] rounded-full py-1 px-3 text-xs font-bold text-[#14141A] shadow-[2px_2px_0_#14141A]">
                <Shield className="w-3.5 h-3.5 text-[#FF6B3D]" />
                <Link href="/admin/dashboard" className="hover:underline">Admin</Link>
                <button onClick={handleAdminLogout} className="text-[#FF6B3D] hover:underline ml-1">
                  &times;
                </button>
              </div>
            )}
          </div>
        </div>
        
        {/* Mobile Menu Button */}
        <div className="relative md:hidden">
          <button 
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="border-2 border-[#14141A] bg-white shadow-[2px_2px_0_#14141A] p-2 rounded-full cursor-pointer"
            aria-label="Toggle Menu"
          >
            <Menu className="w-5 h-5 text-[#14141A]" />
          </button>
          
          {mobileMenuOpen && (
            <div className="absolute right-0 mt-3 z-50 p-3 shadow-[5px_5px_0_#14141A] bg-white border-2 border-[#14141A] rounded-[18px] w-56 flex flex-col gap-1.5 font-bold text-xs animate-slide-up">
              <Link 
                href="/scan" 
                className="p-2 hover:bg-[#F5F4EE] rounded-lg"
                onClick={() => setMobileMenuOpen(false)}
              >
                Scan Code
              </Link>
              {githubUser && (
                <Link 
                  href="/dashboard" 
                  className="p-2 hover:bg-[#F5F4EE] rounded-lg text-[#14141A]"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Repositories
                </Link>
              )}
              <Link 
                href="/examples" 
                className="p-2 hover:bg-[#F5F4EE] rounded-lg"
                onClick={() => setMobileMenuOpen(false)}
              >
                Examples
              </Link>
              <Link 
                href="/history" 
                className="p-2 hover:bg-[#F5F4EE] rounded-lg"
                onClick={() => setMobileMenuOpen(false)}
              >
                Scan History
              </Link>
              <Link 
                href="/privacy" 
                className="p-2 hover:bg-[#F5F4EE] rounded-lg"
                onClick={() => setMobileMenuOpen(false)}
              >
                Privacy &amp; Data Guarantee
              </Link>
              <Link 
                href="/status" 
                className="p-2 hover:bg-[#F5F4EE] rounded-lg"
                onClick={() => setMobileMenuOpen(false)}
              >
                System Status
              </Link>
              
              <div className="border-t border-[#E2E0D6] my-1"></div>
              
              {githubUser ? (
                <button
                  onClick={(e) => {
                    handleGithubLogout(e);
                    setMobileMenuOpen(false);
                  }}
                  className="p-2 text-left text-[#FF6B3D] hover:bg-[#FFD9CC] rounded-lg font-bold flex items-center justify-between"
                >
                  <span>Sign out ({githubUser.github_login})</span>
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              ) : (
                <Link
                  href="/login"
                  className="p-2 bg-[#14141A] text-white rounded-lg text-center"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Sign in with GitHub
                </Link>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
