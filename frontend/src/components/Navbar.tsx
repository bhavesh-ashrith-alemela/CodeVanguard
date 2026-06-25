'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Shield, PlusCircle, Code, History, Lock, LogOut, Menu } from 'lucide-react';
import { useToast } from './ToastProvider';

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { showToast } = useToast();
  
  const [adminUsername, setAdminUsername] = useState<string | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState<boolean>(false);

  const checkAuth = () => {
    if (typeof window !== 'undefined') {
      const username = localStorage.getItem('admin_username');
      setAdminUsername(username);
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

  const handleLogout = (e: React.MouseEvent) => {
    e.preventDefault();
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_username');
    setAdminUsername(null);
    showToast('Logged out successfully.', 'info');
    
    // Dispatch auth-change event
    window.dispatchEvent(new Event('auth-change'));
    
    router.push('/');
  };

  const isScanActive = pathname === '/';
  const isExamplesActive = pathname === '/examples';
  const isHistoryActive = pathname === '/history';
  const isAdminActive = pathname.startsWith('/admin');

  return (
    <div className="sticky top-0 z-50 w-full bg-white border-b-4 border-slate-900">
      <div className="navbar max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between py-2">
        <div className="flex-1">
          <Link href="/" className="flex items-center gap-2 font-black text-xl tracking-tight text-slate-900 hover:opacity-95 transition-all duration-300">
            <Shield className="w-7 h-7 text-primary flex-shrink-0" />
            <span className="font-extrabold tracking-tight text-lg md:text-xl">CodeVanguard</span>
          </Link>
        </div>
        
        <div className="flex-none gap-2">
          {/* Desktop Menu */}
          <ul className="menu menu-horizontal px-1 font-extrabold gap-2 hidden md:flex text-xs flex-row list-none">
            <li>
              <Link href="/" className={`hover:bg-primary/10 hover:text-primary rounded-lg transition-all py-1.5 px-3 border-2 border-transparent block ${isScanActive ? 'text-primary bg-primary/5 border-slate-900' : ''}`}>
                <PlusCircle className="w-4 h-4 inline mr-1" /> Scan
              </Link>
            </li>
            <li>
              <Link href="/examples" className={`hover:bg-primary/10 hover:text-primary rounded-lg transition-all py-1.5 px-3 border-2 border-transparent block ${isExamplesActive ? 'text-primary bg-primary/5 border-slate-900' : ''}`}>
                <Code className="w-4 h-4 inline mr-1" /> Examples
              </Link>
            </li>
            <li>
              <Link href="/history" className={`hover:bg-primary/10 hover:text-primary rounded-lg transition-all py-1.5 px-3 border-2 border-transparent block ${isHistoryActive ? 'text-primary bg-primary/5 border-slate-900' : ''}`}>
                <History className="w-4 h-4 inline mr-1" /> History
              </Link>
            </li>
            {adminUsername ? (
              <>
                <li>
                  <Link href="/admin/dashboard" className={`hover:bg-primary/10 hover:text-primary rounded-lg transition-all py-1.5 px-3 border-2 border-transparent block ${pathname === '/admin/dashboard' ? 'text-primary bg-primary/5 border-slate-900' : ''}`}>
                    <Shield className="w-4 h-4 inline mr-1" /> Dashboard
                  </Link>
                </li>
                <li>
                  <button onClick={handleLogout} className="hover:bg-red-50 hover:text-red-600 text-red-500 rounded-lg transition-all py-1.5 px-3 border-2 border-transparent cursor-pointer font-extrabold text-xs">
                    <LogOut className="w-4 h-4 inline mr-1" /> Logout
                  </button>
                </li>
              </>
            ) : (
              <li>
                <Link href="/admin/login" className={`hover:bg-primary/10 hover:text-primary rounded-lg transition-all py-1.5 px-3 border-2 border-transparent block ${pathname === '/admin/login' ? 'text-primary bg-primary/5 border-slate-900' : ''}`}>
                  <Lock className="w-4 h-4 inline mr-1" /> Admin
                </Link>
              </li>
            )}
          </ul>
          
          {/* Mobile Menu Dropdown */}
          <div className="relative md:hidden">
            <button 
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="border-2 border-slate-900 bg-white shadow-[2px_2px_0px_#0f172a] hover:bg-slate-50 flex items-center justify-center w-10 h-10 rounded-full cursor-pointer transition-all active:translate-y-[1px] active:shadow-[1px_1px_0px_#0f172a]"
              aria-label="Toggle Menu"
            >
              <Menu className="w-5 h-5" />
            </button>
            
            {mobileMenuOpen && (
              <ul className="absolute right-0 mt-3 z-50 p-2 shadow-[4px_4px_0px_#0f172a] bg-white border-4 border-slate-900 rounded-xl w-52 text-slate-800 font-extrabold text-xs list-none animate-slide-up">
                <li className="my-1">
                  <Link 
                    href="/" 
                    className="block p-2 hover:bg-slate-100 rounded-md"
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    <PlusCircle className="w-4 h-4 inline mr-2 text-primary" />Scan
                  </Link>
                </li>
                <li className="my-1">
                  <Link 
                    href="/examples" 
                    className="block p-2 hover:bg-slate-100 rounded-md"
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    <Code className="w-4 h-4 inline mr-2 text-primary" />Examples
                  </Link>
                </li>
                <li className="my-1">
                  <Link 
                    href="/history" 
                    className="block p-2 hover:bg-slate-100 rounded-md"
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    <History className="w-4 h-4 inline mr-2 text-primary" />History
                  </Link>
                </li>
                <div className="divider my-1 border-t-2 border-slate-200"></div>
                {adminUsername ? (
                  <>
                    <li className="my-1">
                      <Link 
                        href="/admin/dashboard" 
                        className="block p-2 text-primary hover:bg-slate-100 rounded-md"
                        onClick={() => setMobileMenuOpen(false)}
                      >
                        <Shield className="w-4 h-4 inline mr-2" />Dashboard
                      </Link>
                    </li>
                    <li className="my-1">
                      <button 
                        onClick={(e) => {
                          handleLogout(e);
                          setMobileMenuOpen(false);
                        }} 
                        className="block w-full text-left p-2 text-red-500 hover:bg-slate-100 rounded-md font-extrabold cursor-pointer"
                      >
                        <LogOut className="w-4 h-4 inline mr-2" />Logout
                      </button>
                    </li>
                  </>
                ) : (
                  <li className="my-1">
                    <Link 
                      href="/admin/login" 
                      className="block p-2 hover:bg-slate-100 rounded-md"
                      onClick={() => setMobileMenuOpen(false)}
                    >
                      <Lock className="w-4 h-4 inline mr-2 text-primary" />Admin Portal
                    </Link>
                  </li>
                )}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
