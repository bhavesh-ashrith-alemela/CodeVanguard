'use client';

import React, { useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { UploadCloud, TextCursor, Shield, FolderArchive, FileCode, Zap, Target, ShieldCheck, Award } from 'lucide-react';
import { useToast } from '@/components/ToastProvider';
import { fetchApi } from '@/lib/api';

export default function Home() {
  const router = useRouter();
  const { showToast } = useToast();
  
  const [activeTab, setActiveTab] = useState<'upload' | 'paste'>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [code, setCode] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [dragActive, setDragActive] = useState<boolean>(false);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const validateAndSetFile = (selectedFile: File) => {
    const maxBytes = 10 * 1024 * 1024;
    if (selectedFile.size > maxBytes) {
      showToast("File size exceeds maximum limit of 10MB.", "error");
      if (fileInputRef.current) fileInputRef.current.value = '';
      setFile(null);
      return;
    }
    
    setFile(selectedFile);
    showToast(`Loaded ${selectedFile.name} successfully!`, 'success');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const formData = new FormData();
      
      if (activeTab === 'upload') {
        if (!file) {
          throw new Error("Please upload a file or ZIP archive first.");
        }
        formData.append('file', file);
      } else {
        if (!code || !code.trim()) {
          throw new Error("Please paste your Python code to initialize scanning.");
        }
        formData.append('code', code);
      }

      const response = await fetchApi('/api/scan/json', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Server rejected scan request.");
      }

      const result = await response.json();
      showToast("Scan successfully scheduled! Loading report terminal...", "success");
      
      setTimeout(() => {
        router.push(`/results?id=${result.scan_id}`);
      }, 1000);

    } catch (error: any) {
      showToast(error.message || "An error occurred while submitting scan.", "error");
      setLoading(false);
    }
  };

  const isSubmitDisabled = activeTab === 'upload' ? !file || loading : !code.trim() || loading;

  return (
    <div className="max-w-4xl mx-auto space-y-12 animate-slide-up w-full">
      
      {/* Hero / Headline Section */}
      <div className="text-center space-y-4 py-4">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border-4 border-slate-900 bg-white shadow-[2px_2px_0px_#000] text-primary text-xs font-black tracking-widest uppercase">
          <span className="w-2.5 h-2.5 rounded-full bg-primary animate-ping"></span>
          DEFENSE STATION ONLINE
        </div>
        <h1 className="text-4xl md:text-5xl font-black tracking-tight text-slate-900 leading-tight">
          SECURE YOUR CODEBASE <br className="hidden sm:inline" />
          <span className="text-primary uppercase tracking-wide text-3xl md:text-4xl font-black block mt-2">Level Up Your Defenses</span>
        </h1>
        <p className="max-w-xl mx-auto text-slate-500 text-xs font-bold leading-relaxed">
          Concurrently execute Bandit AST and Semgrep pattern checkers. Find security defects and review side-by-side secure patches to clear the level!
        </p>
      </div>

      {/* Main Scanner Box (Cartoon Window Style) */}
      <div className="cartoon-card">
        
        {/* Window Decor header */}
        <div className="window-header bg-slate-900 text-white border-b-4 border-slate-900 flex items-center justify-between px-4 py-2 select-none">
          <div className="window-dots flex gap-1.5">
            <span className="w-3.5 h-3.5 rounded-full bg-red-450 border-2 border-slate-900 bg-[#f87171]"></span>
            <span className="w-3.5 h-3.5 rounded-full bg-yellow-450 border-2 border-slate-900 bg-[#fbbf24]"></span>
            <span className="w-3.5 h-3.5 rounded-full bg-green-450 border-2 border-slate-900 bg-[#34d399]"></span>
          </div>
          <span className="text-[10px] font-black uppercase tracking-widest font-mono text-slate-300">security_scan_terminal.py</span>
          <div className="w-12"></div>
        </div>

        <div className="p-6 md:p-8 space-y-6">
          {/* Tab Controllers */}
          <div role="tablist" className="flex items-center justify-center gap-3 mb-8 max-w-md mx-auto">
            <button
              type="button"
              className={`cartoon-btn inline-flex items-center justify-center gap-1.5 text-xs px-5 py-2 rounded-full ${activeTab === 'upload' ? 'active' : 'inactive'}`}
              onClick={() => setActiveTab('upload')}
            >
              <UploadCloud className="w-4 h-4" /> Upload File / ZIP
            </button>
            <button
              type="button"
              className={`cartoon-btn inline-flex items-center justify-center gap-1.5 text-xs px-5 py-2 rounded-full ${activeTab === 'paste' ? 'active' : 'inactive'}`}
              onClick={() => setActiveTab('paste')}
            >
              <TextCursor className="w-4 h-4" /> Paste Source
            </button>
          </div>

          {/* Forms Container */}
          <form onSubmit={handleSubmit} className="space-y-6">
            
            {/* Tab 1: Upload */}
            {activeTab === 'upload' && (
              <div className="tab-content block">
                <div className="space-y-4">
                  <div
                    onDragEnter={handleDrag}
                    onDragOver={handleDrag}
                    onDragLeave={handleDrag}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                    className={`flex flex-col items-center justify-center w-full h-64 border-4 border-dashed border-slate-900 rounded-2xl cursor-pointer shadow-[4px_4px_0px_#cbd5e1] hover:shadow-[2px_2px_0px_#0f172a] transition-all duration-200 ${
                      dragActive ? 'bg-slate-100 border-primary' : 'bg-slate-50/50 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex flex-col items-center justify-center pt-5 pb-6 text-center px-4">
                      <span className="p-3.5 bg-primary/10 rounded-2xl text-primary mb-4 border-4 border-slate-900 shadow-[2px_2px_0px_#0f172a] inline-flex">
                        <Shield className="w-8 h-8" />
                      </span>
                      <p className="mb-1 text-sm text-slate-800 font-extrabold uppercase tracking-wide">
                        Drag and drop codebase
                      </p>
                      <p className="text-[10px] text-slate-400 font-bold">
                        Supports single <span className="text-primary font-bold font-mono">.py</span> files or compressed <span className="text-primary font-bold font-mono">.zip</span> archives (Max 10MB)
                      </p>
                    </div>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".py,.zip"
                      className="hidden"
                      onChange={handleFileChange}
                    />
                  </div>
                  
                  {/* Selected File Metadata Details */}
                  {file && (
                    <div className="animate-slide-up text-center flex justify-center">
                      <div className="flex items-center gap-3 bg-slate-900/10 p-3 rounded-lg border border-slate-900/10 text-left">
                        <span className="p-2 bg-primary/20 rounded-md text-primary inline-flex">
                          {file.name.endsWith('.zip') ? <FolderArchive className="w-5 h-5" /> : <FileCode className="w-5 h-5" />}
                        </span>
                        <div>
                          <p className="font-semibold text-slate-800 truncate max-w-[200px] sm:max-w-xs">{file.name}</p>
                          <p className="text-xs text-slate-500 font-bold">{(file.size / 1024).toFixed(1)} KB</p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Tab 2: Paste Code */}
            {activeTab === 'paste' && (
              <div className="tab-content block space-y-4">
                <div className="form-control">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-extrabold text-slate-600 uppercase tracking-widest">Input Buffer</span>
                    <span className="text-[9px] text-slate-400 font-mono font-bold">pasted_code.py</span>
                  </div>
                  <textarea
                    name="code"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="# Paste your Python code here...&#10;import sqlite3&#10;def get_user(username):&#10;    conn = sqlite3.connect('database.db')&#10;    cursor = conn.cursor()&#10;    cursor.execute(f&quot;SELECT * FROM users WHERE username = '{username}'&quot;)&#10;    return cursor.fetchone()"
                    className="cartoon-input textarea h-64 w-full font-mono text-xs p-4 leading-relaxed text-slate-800 focus:outline-none"
                  ></textarea>
                </div>
              </div>
            )}

            {/* Submit trigger button */}
            <div className="text-center pt-2">
              <button
                type="submit"
                disabled={isSubmitDisabled}
                className="cartoon-btn btn-lg px-12 py-3.5 rounded-xl font-black text-sm text-white flex items-center justify-center mx-auto gap-2 min-w-[240px]"
              >
                <Zap className={`w-5 h-5 ${loading ? 'animate-spin' : 'animate-bounce'}`} />
                {loading ? 'Analyzing Codebase...' : 'Initialize Scan Quest'}
              </button>
            </div>
            
          </form>
        </div>
      </div>

      {/* Quick instructions / value props */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4">
        <div className="cartoon-card p-6 space-y-3 bg-white">
          <span className="p-2.5 bg-primary/10 rounded-xl text-primary inline-block border-2 border-slate-900 shadow-[2px_2px_0px_#0f172a]">
            <Target className="w-5 h-5" />
          </span>
          <h3 className="font-black text-slate-800 text-xs uppercase tracking-wider">Quest 1: Scan & Detect</h3>
          <p className="text-xs text-slate-550 font-bold leading-relaxed">Concurrently execute Bandit AST analyzers and Semgrep pattern matchers to uncover security defects and credentials leaks.</p>
        </div>
        
        <div className="cartoon-card p-6 space-y-3 bg-white">
          <span className="p-2.5 bg-primary/10 rounded-xl text-primary inline-block border-2 border-slate-900 shadow-[2px_2px_0px_#0f172a]">
            <ShieldCheck className="w-5 h-5" />
          </span>
          <h3 className="font-black text-slate-800 text-xs uppercase tracking-wider">Quest 2: Remediation</h3>
          <p className="text-xs text-slate-555 font-bold leading-relaxed">Review context-rich code snippets matched with clean, side-by-side secured patches to level-up code security.</p>
        </div>
        
        <div className="cartoon-card p-6 space-y-3 bg-white">
          <span className="p-2.5 bg-primary/10 rounded-xl text-primary inline-block border-2 border-slate-900 shadow-[2px_2px_0px_#0f172a]">
            <Award className="w-5 h-5" />
          </span>
          <h3 className="font-black text-slate-800 text-xs uppercase tracking-wider">Quest 3: Exporters</h3>
          <p className="text-xs text-slate-555 font-bold leading-relaxed">Synthesize final scan scores and achievements into standard PDF, HTML, JSON, or CSV compliance formats.</p>
        </div>
      </div>
    </div>
  );
}
