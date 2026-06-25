'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Lock, User, Key, Loader2 } from 'lucide-react';
import { useToast } from '@/components/ToastProvider';
import { fetchApi } from '@/lib/api';

export default function AdminLoginPage() {
  const router = useRouter();
  const { showToast } = useToast();
  
  const [username, setUsername] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    if (typeof window !== 'undefined' && localStorage.getItem('admin_token')) {
      router.push('/admin/dashboard');
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const response = await fetchApi('/api/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, password })
      });

      if (!response.ok) {
        const errorMsg = response.status === 401 
          ? "Invalid username or password." 
          : response.status === 429 
            ? "Too many failed attempts. Please wait 15 minutes." 
            : "Server authentication error.";
        throw new Error(errorMsg);
      }

      const data = await response.json();
      
      localStorage.setItem('admin_token', data.token);
      localStorage.setItem('admin_username', data.username);
      
      // Dispatch custom event to notify Navbar component
      window.dispatchEvent(new Event('auth-change'));
      
      showToast("Admin authenticated successfully! Redirecting...", "success");
      
      setTimeout(() => {
        router.push('/admin/dashboard');
      }, 1000);

    } catch (error: any) {
      showToast(error.message || "Failed to log in.", "error");
      setLoading(false);
    }
  };

  return (
    <div className="flex-grow flex items-center justify-center py-12">
      <div className="w-full max-w-md animate-slide-up">
        
        <div className="cartoon-card">
          {/* Window Decor header */}
          <div className="window-header bg-slate-900 text-white flex items-center justify-between px-4 py-2 border-b-4 border-slate-900 select-none">
            <span className="text-[10px] font-black uppercase tracking-widest font-mono text-slate-300">admin_login_terminal.exe</span>
            <div className="window-dots flex gap-1.5">
              <span className="w-3.5 h-3.5 rounded-full bg-red-400 border-2 border-slate-900 bg-[#f87171]"></span>
              <span className="w-3.5 h-3.5 rounded-full bg-slate-700 bg-slate-650"></span>
            </div>
          </div>

          <div className="p-6 md:p-8 space-y-6 bg-white bg-white">
            <div className="text-center space-y-1.5">
              <h3 className="text-lg font-black text-slate-800 uppercase tracking-wide">Enter Admin Credentials</h3>
              <p className="text-[10px] text-slate-400 font-bold">Provide secure credentials to enter the system dashboard.</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="form-control">
                <label className="label">
                  <span className="label-text text-[10px] font-black uppercase text-slate-555 tracking-wider">Access Identifier (Username)</span>
                </label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400 pointer-events-none">
                    <User className="w-4 h-4" />
                  </span>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="admin"
                    required
                    className="cartoon-input input w-full pl-10 text-xs text-slate-800 p-2.5 border-4"
                  />
                </div>
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text text-[10px] font-black uppercase text-slate-555 tracking-wider">Security Key (Password)</span>
                </label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400 pointer-events-none">
                    <Key className="w-4 h-4" />
                  </span>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    className="cartoon-input input w-full pl-10 text-xs text-slate-800 p-2.5 border-4"
                  />
                </div>
              </div>

              <div className="pt-4">
                <button 
                  type="submit" 
                  disabled={loading}
                  className="cartoon-btn w-full py-3 rounded-xl text-xs font-black text-white flex items-center justify-center gap-1.5 cursor-pointer"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Establishing session...
                    </>
                  ) : (
                    <>
                      <Lock className="w-4 h-4" />
                      Establish Access
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
        
      </div>
    </div>
  );
}
