'use client';

import React, { useState, useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { 
  Shield, UploadCloud, FolderArchive, FileCode, Zap, Sparkles, 
  Link2, GitBranch, AlertCircle, RefreshCw, CheckCircle2, ArrowRight,
  ShieldCheck, Terminal, Award, Target
} from 'lucide-react';
import { fetchApi } from '@/lib/api';

const CODE_EXAMPLES: Record<'py' | 'js' | 'ts' | 'go', string> = {
  py: `# Python SAST Vulnerability Demo: SQL Injection & Subprocess Shell
import sqlite3
import subprocess

def search_user(username: str):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # CRITICAL: Insecure string interpolation in SQL query (CWE-89)
    cursor.execute(f"SELECT * FROM accounts WHERE user = '{username}'")
    return cursor.fetchall()

def run_backup(path: str):
    # HIGH: shell=True command injection (CWE-78)
    subprocess.Popen(f"tar -czf backup.tar.gz {path}", shell=True)
`,
  js: `// JavaScript/Node.js SAST Vulnerability Demo: Command Injection & Dynamic Eval
const express = require('express');
const { exec } = require('child_process');
const app = express();

app.get('/ping', (req, res) => {
    const host = req.query.host;
    // CRITICAL: Unsanitized input passed directly to child_process.exec (CWE-78)
    exec(\`ping -c 1 \${host}\`, (err, stdout) => {
        res.send(stdout);
    });
});

app.post('/calculate', (req, res) => {
    // CRITICAL: Dynamic code execution via eval (CWE-95)
    const result = eval(req.body.expression);
    res.json({ result });
});
`,
  ts: `// TypeScript / React Vulnerability Demo: XSS & Path Traversal
import React from 'react';
import fs from 'fs';
import path from 'path';

export const UserBio = ({ rawBioHtml }: { rawBioHtml: string }) => {
    // HIGH: Direct unescaped HTML injection via dangerouslySetInnerHTML (CWE-79)
    return <div dangerouslySetInnerHTML={{ __html: rawBioHtml }} />;
};

export function readUserFile(userInputPath: string) {
    // HIGH: Path traversal vulnerability (CWE-22)
    const target = path.join('/var/data/uploads', userInputPath);
    return fs.readFileSync(target, 'utf-8');
}
`,
  go: `// Go SAST Vulnerability Demo: Raw SQL Query Construction
package main

import (
    "database/sql"
    "fmt"
    _ "github.com/lib/pq"
)

func findAccount(db *sql.DB, accountName string) (*sql.Rows, error) {
    // CRITICAL: Raw string concatenation in SQL statement (CWE-89)
    query := fmt.Sprintf("SELECT id, balance FROM accounts WHERE name = '%s'", accountName)
    return db.Query(query)
}
`
};

export default function ScanPage() {
  const router = useRouter();

  const [activeTab, setActiveTab] = useState<'upload' | 'paste' | 'repo'>('upload');

  // Upload ZIP state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Paste Code state
  const [pastedCode, setPastedCode] = useState(CODE_EXAMPLES.py);
  const [pastedLang, setPastedLang] = useState<'py' | 'js' | 'ts' | 'go'>('py');
  const [pasteLoading, setPasteLoading] = useState(false);
  const [pasteError, setPasteError] = useState<string | null>(null);

  // Repo URL state
  const [repoUrl, setRepoUrl] = useState('');
  const [repoBranch, setRepoBranch] = useState('');
  const [repoLoading, setRepoLoading] = useState(false);
  const [repoError, setRepoError] = useState<string | null>(null);

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) {
      setUploadError('Please select a .zip archive or source file to scan.');
      return;
    }
    setUploadError(null);
    setUploadLoading(true);

    try {
      const formData = new FormData();
      formData.append('file', uploadFile);

      const res = await fetchApi('/api/scan/json', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to submit file for scanning');
      }

      const data = await res.json();
      router.push(`/results?id=${data.scan_id}`);
    } catch (err: any) {
      setUploadError(err.message || 'File upload failed');
      setUploadLoading(false);
    }
  };

  const handlePasteScan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pastedCode.trim()) {
      setPasteError('Please enter some code to analyze.');
      return;
    }
    setPasteError(null);
    setPasteLoading(true);

    try {
      const formData = new FormData();
      formData.append('code', pastedCode);
      formData.append('extension', pastedLang);

      const res = await fetchApi('/api/scan/json', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to submit code for scanning');
      }

      const data = await res.json();
      router.push(`/results?id=${data.scan_id}`);
    } catch (err: any) {
      setPasteError(err.message || 'Code analysis failed');
      setPasteLoading(false);
    }
  };

  const handleRepoScan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.trim()) {
      setRepoError('Please enter a GitHub repository URL.');
      return;
    }
    setRepoError(null);
    setRepoLoading(true);

    try {
      const payload: Record<string, string> = { url: repoUrl.trim() };
      if (repoBranch.trim()) {
        payload.branch = repoBranch.trim();
      }

      const res = await fetchApi('/api/scan/repo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to scan repository');
      }

      const data = await res.json();
      router.push(`/results?id=${data.scan_id}`);
    } catch (err: any) {
      setRepoError(err.message || 'Repository scan failed');
      setRepoLoading(false);
    }
  };

  return (
    <div className="max-w-[960px] mx-auto px-4 sm:px-6 lg:px-8 py-8 md:py-12 flex flex-col gap-10">
      
      {/* Hero / Terminal Header */}
      <div className="text-center flex flex-col items-center gap-3">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border-2 border-[#14141A] bg-[#D6F25B] text-[#14141A] font-mono text-xs font-black tracking-wider uppercase shadow-[2px_2px_0_#14141A]">
          <span className="w-2 h-2 rounded-full bg-[#14141A] animate-ping" />
          <span>DEFENSE STATION ONLINE</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-black text-[#14141A] tracking-tight">
          SECURE YOUR CODEBASE
        </h1>
        <p className="text-sm sm:text-base text-[#55555F] max-w-xl font-medium leading-relaxed">
          Upload a ZIP archive, paste raw source code, or insert a GitHub URL to trigger dual Bandit AST and Semgrep SAST security scanners in real-time.
        </p>
      </div>

      {/* Main Terminal Window */}
      <div className="border-2 border-[#14141A] rounded-[22px] bg-white shadow-[6px_6px_0_#14141A] overflow-hidden">
        
        {/* Terminal Header Bar */}
        <div className="bg-[#14141A] text-white px-4 py-3 border-b-2 border-[#14141A] flex items-center justify-between select-none">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-[#FF6B3D] border border-[#14141A]" />
            <span className="w-3 h-3 rounded-full bg-[#FFC93C] border border-[#14141A]" />
            <span className="w-3 h-3 rounded-full bg-[#D6F25B] border border-[#14141A]" />
          </div>
          <span className="font-mono text-xs font-bold text-[#A5A4AF] flex items-center gap-1.5">
            <Terminal className="w-3.5 h-3.5 text-[#D6F25B]" />
            <span>codevanguard_scan_station.py</span>
          </span>
          <div className="w-10" />
        </div>

        {/* Tab Switcher */}
        <div className="p-4 sm:p-6 border-b-2 border-[#14141A] bg-[#FAF9F5]">
          <div className="flex flex-wrap items-center justify-center gap-2 max-w-lg mx-auto">
            <button
              type="button"
              onClick={() => setActiveTab('upload')}
              className={`inline-flex items-center gap-2 px-5 py-2 rounded-full font-bold text-xs border-2 border-[#14141A] cursor-pointer transition-all ${
                activeTab === 'upload'
                  ? 'bg-[#14141A] text-[#F5F4EE] shadow-[2px_2px_0_#D6F25B]'
                  : 'bg-white text-[#14141A] shadow-[2px_2px_0_#14141A] hover:bg-[#F5F4EE]'
              }`}
            >
              <UploadCloud className="w-4 h-4 text-[#D6F25B]" />
              <span>Upload File / ZIP</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('paste')}
              className={`inline-flex items-center gap-2 px-5 py-2 rounded-full font-bold text-xs border-2 border-[#14141A] cursor-pointer transition-all ${
                activeTab === 'paste'
                  ? 'bg-[#14141A] text-[#F5F4EE] shadow-[2px_2px_0_#B8A2FF]'
                  : 'bg-white text-[#14141A] shadow-[2px_2px_0_#14141A] hover:bg-[#F5F4EE]'
              }`}
            >
              <FileCode className="w-4 h-4 text-[#B8A2FF]" />
              <span>Paste Code</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('repo')}
              className={`inline-flex items-center gap-2 px-5 py-2 rounded-full font-bold text-xs border-2 border-[#14141A] cursor-pointer transition-all ${
                activeTab === 'repo'
                  ? 'bg-[#14141A] text-[#F5F4EE] shadow-[2px_2px_0_#FFC93C]'
                  : 'bg-white text-[#14141A] shadow-[2px_2px_0_#14141A] hover:bg-[#F5F4EE]'
              }`}
            >
              <Link2 className="w-4 h-4 text-[#FFC93C]" />
              <span>Git Repo URL</span>
            </button>
          </div>
        </div>

        {/* Tab Content Panes */}
        <div className="p-6 sm:p-8">

          {/* TAB 1: UPLOAD FILE / ZIP */}
          {activeTab === 'upload' && (
            <form onSubmit={handleFileUpload} className="flex flex-col gap-5">
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  if (e.dataTransfer.files?.[0]) {
                    setUploadFile(e.dataTransfer.files[0]);
                  }
                }}
                onClick={() => fileInputRef.current?.click()}
                className={`flex flex-col items-center justify-center p-8 sm:p-12 border-2 border-dashed rounded-2xl cursor-pointer transition-all ${
                  isDragging 
                    ? 'border-[#14141A] bg-[#E8F8B6]' 
                    : 'border-[#14141A] bg-[#FAF9F5] hover:bg-[#F5F4EE]'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip,.py,.js,.ts,.go,.jsx,.tsx"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files?.[0]) {
                      setUploadFile(e.target.files[0]);
                    }
                  }}
                />

                <div className="p-4 rounded-2xl bg-[#D6F25B] border-2 border-[#14141A] shadow-[2px_2px_0_#14141A] mb-3">
                  <FolderArchive className="w-8 h-8 text-[#14141A]" />
                </div>

                <p className="font-black text-base text-[#14141A] mb-1 text-center">
                  Drag and drop your codebase or browse
                </p>
                <p className="font-mono text-xs text-[#55555F] text-center">
                  Supports compressed <span className="font-bold text-[#14141A]">.zip</span> archives or individual <span className="font-bold text-[#14141A]">.py, .js, .ts, .go</span> files (Max 10MB)
                </p>

                {uploadFile && (
                  <div className="mt-4 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border-2 border-[#14141A] bg-white font-mono text-xs font-bold text-[#14141A] shadow-[2px_2px_0_#14141A]">
                    <CheckCircle2 className="w-4 h-4 text-[#10B981]" />
                    <span>{uploadFile.name}</span>
                    <span className="text-[#888893]">({(uploadFile.size / 1024).toFixed(1)} KB)</span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setUploadFile(null);
                        if (fileInputRef.current) fileInputRef.current.value = '';
                      }}
                      className="ml-1 text-[#55555F] hover:text-[#FF6B3D]"
                    >
                      &times;
                    </button>
                  </div>
                )}
              </div>

              {uploadError && (
                <div className="flex items-center gap-2.5 p-3 rounded-xl border-2 border-[#FF6B3D] bg-[#FFF2EE] text-[#14141A] font-mono text-xs font-bold">
                  <AlertCircle className="w-4 h-4 text-[#FF6B3D] flex-shrink-0" />
                  <span>{uploadError}</span>
                </div>
              )}

              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  disabled={uploadLoading || !uploadFile}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-7 py-3 border-2 border-[#14141A] rounded-xl bg-[#D6F25B] text-[#14141A] font-bold text-sm shadow-[3px_3px_0_#14141A] hover:bg-[#c6e448] disabled:opacity-50 disabled:cursor-not-allowed active:translate-x-0.5 active:translate-y-0.5 active:shadow-none transition-all cursor-pointer"
                >
                  {uploadLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Uploading &amp; Scanning...</span>
                    </>
                  ) : (
                    <>
                      <Zap className="w-4 h-4" />
                      <span>Initialize Scan Quest</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

          {/* TAB 2: PASTE CODE */}
          {activeTab === 'paste' && (
            <form onSubmit={handlePasteScan} className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-[#E2E0D6]">
                <div className="inline-flex items-center gap-1 p-1 rounded-full border border-[#14141A] bg-white">
                  {(['py', 'js', 'ts', 'go'] as const).map((lang) => (
                    <button
                      key={lang}
                      type="button"
                      onClick={() => {
                        setPastedLang(lang);
                        setPastedCode(CODE_EXAMPLES[lang]);
                      }}
                      className={`px-3 py-1 rounded-full font-mono text-xs font-bold transition-all cursor-pointer ${
                        pastedLang === lang
                          ? 'bg-[#14141A] text-white shadow-[1px_1px_0_#D6F25B]'
                          : 'text-[#14141A] hover:bg-[#F5F4EE]'
                      }`}
                    >
                      {lang === 'py' ? 'Python' : lang === 'js' ? 'JavaScript' : lang === 'ts' ? 'TypeScript' : 'Go'}
                    </button>
                  ))}
                </div>

                <button
                  type="button"
                  onClick={() => setPastedCode(CODE_EXAMPLES[pastedLang])}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-[#14141A] bg-white text-[#14141A] font-mono text-[11px] font-bold hover:bg-[#F5F4EE] cursor-pointer shadow-[1px_1px_0_#14141A]"
                >
                  <Sparkles className="w-3 h-3 text-[#B8A2FF]" />
                  <span>Reload Vulnerability Sample</span>
                </button>
              </div>

              <div className="relative border-2 border-[#14141A] rounded-xl overflow-hidden shadow-[2px_2px_0_#14141A] bg-[#14141A]">
                <div className="flex items-center justify-between px-3.5 py-2 bg-[#2B2B36] text-[#D0CFD8] font-mono text-[11px] border-b border-[#3C3C46]">
                  <span>buffer.{pastedLang}</span>
                  <span>{pastedCode.split('\n').length} lines · {pastedCode.length} chars</span>
                </div>
                <textarea
                  value={pastedCode}
                  onChange={(e) => setPastedCode(e.target.value)}
                  placeholder={`# Paste your ${pastedLang.toUpperCase()} code here to analyze...`}
                  rows={12}
                  className="w-full p-4 font-mono text-xs leading-relaxed bg-[#14141A] text-[#F5F4EE] placeholder:text-[#55555F] focus:outline-none resize-y"
                  spellCheck={false}
                />
              </div>

              {pasteError && (
                <div className="flex items-center gap-2.5 p-3 rounded-xl border-2 border-[#FF6B3D] bg-[#FFF2EE] text-[#14141A] font-mono text-xs font-bold">
                  <AlertCircle className="w-4 h-4 text-[#FF6B3D] flex-shrink-0" />
                  <span>{pasteError}</span>
                </div>
              )}

              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  disabled={pasteLoading || !pastedCode.trim()}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-7 py-3 border-2 border-[#14141A] rounded-xl bg-[#D6F25B] text-[#14141A] font-bold text-sm shadow-[3px_3px_0_#14141A] hover:bg-[#c6e448] disabled:opacity-50 disabled:cursor-not-allowed active:translate-x-0.5 active:translate-y-0.5 active:shadow-none transition-all cursor-pointer"
                >
                  {pasteLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Analyzing Code...</span>
                    </>
                  ) : (
                    <>
                      <Zap className="w-4 h-4" />
                      <span>Scan Code Buffer</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

          {/* TAB 3: GIT REPOSITORY URL */}
          {activeTab === 'repo' && (
            <form onSubmit={handleRepoScan} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="font-mono text-xs font-bold text-[#14141A]">
                  GitHub Repository URL <span className="text-[#FF6B3D]">*</span>
                </label>
                <div className="relative">
                  <input
                    type="url"
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    placeholder="https://github.com/owner/repository"
                    required
                    className="w-full px-3.5 py-2.5 pl-10 border-2 border-[#14141A] rounded-xl font-mono text-xs bg-white text-[#14141A] placeholder:text-[#888893] focus:outline-none focus:ring-2 focus:ring-[#D6F25B]"
                  />
                  <Link2 className="w-4 h-4 text-[#55555F] absolute left-3.5 top-3" />
                </div>
                <span className="font-mono text-[11px] text-[#55555F]">
                  Enter any public GitHub repository link to immediately clone and scan.
                </span>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="font-mono text-xs font-bold text-[#14141A]">
                  Branch <span className="text-[#55555F] font-normal">(optional, defaults to primary branch)</span>
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={repoBranch}
                    onChange={(e) => setRepoBranch(e.target.value)}
                    placeholder="e.g. main, master, staging"
                    className="w-full px-3.5 py-2.5 pl-10 border-2 border-[#14141A] rounded-xl font-mono text-xs bg-white text-[#14141A] placeholder:text-[#888893] focus:outline-none focus:ring-2 focus:ring-[#D6F25B]"
                  />
                  <GitBranch className="w-4 h-4 text-[#55555F] absolute left-3.5 top-3" />
                </div>
              </div>

              {repoError && (
                <div className="flex items-center gap-2.5 p-3 rounded-xl border-2 border-[#FF6B3D] bg-[#FFF2EE] text-[#14141A] font-mono text-xs font-bold">
                  <AlertCircle className="w-4 h-4 text-[#FF6B3D] flex-shrink-0" />
                  <span>{repoError}</span>
                </div>
              )}

              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  disabled={repoLoading || !repoUrl.trim()}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-7 py-3 border-2 border-[#14141A] rounded-xl bg-[#D6F25B] text-[#14141A] font-bold text-sm shadow-[3px_3px_0_#14141A] hover:bg-[#c6e448] disabled:opacity-50 disabled:cursor-not-allowed active:translate-x-0.5 active:translate-y-0.5 active:shadow-none transition-all cursor-pointer"
                >
                  {repoLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Cloning &amp; Scanning Repo...</span>
                    </>
                  ) : (
                    <>
                      <Zap className="w-4 h-4" />
                      <span>Scan Repository</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

        </div>
      </div>

      {/* 3 Gamified Quests Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="border-2 border-[#14141A] rounded-[18px] bg-white p-5 shadow-[4px_4px_0_#14141A] flex flex-col gap-2.5">
          <div className="w-9 h-9 rounded-xl border-2 border-[#14141A] bg-[#D6F25B] flex items-center justify-center shadow-[2px_2px_0_#14141A]">
            <Target className="w-5 h-5 text-[#14141A]" />
          </div>
          <span className="font-mono text-[11px] font-black text-[#55555F] uppercase tracking-wider">QUEST 1</span>
          <h3 className="font-bold text-base text-[#14141A]">Concurrent AST Scan</h3>
          <p className="text-xs text-[#55555F] leading-relaxed">
            Bandit AST engine scans Python syntax trees while Semgrep pattern rules simultaneously check for CWE-89, CWE-78, secrets, and hardcoded tokens.
          </p>
        </div>

        <div className="border-2 border-[#14141A] rounded-[18px] bg-white p-5 shadow-[4px_4px_0_#14141A] flex flex-col gap-2.5">
          <div className="w-9 h-9 rounded-xl border-2 border-[#14141A] bg-[#B8A2FF] flex items-center justify-center shadow-[2px_2px_0_#14141A]">
            <ShieldCheck className="w-5 h-5 text-[#14141A]" />
          </div>
          <span className="font-mono text-[11px] font-black text-[#55555F] uppercase tracking-wider">QUEST 2</span>
          <h3 className="font-bold text-base text-[#14141A]">Remediation Patches</h3>
          <p className="text-xs text-[#55555F] leading-relaxed">
            Review context-rich diffs and compiler-verified secure code patches side-by-side to eliminate vulnerabilities before shipping.
          </p>
        </div>

        <div className="border-2 border-[#14141A] rounded-[18px] bg-white p-5 shadow-[4px_4px_0_#14141A] flex flex-col gap-2.5">
          <div className="w-9 h-9 rounded-xl border-2 border-[#14141A] bg-[#FFC93C] flex items-center justify-center shadow-[2px_2px_0_#14141A]">
            <Award className="w-5 h-5 text-[#14141A]" />
          </div>
          <span className="font-mono text-[11px] font-black text-[#55555F] uppercase tracking-wider">QUEST 3</span>
          <h3 className="font-bold text-base text-[#14141A]">Audit Exports</h3>
          <p className="text-xs text-[#55555F] leading-relaxed">
            Export scan artifacts to PDF security audits, HTML standalone dashboards, JSON machine format, CSV, and SARIF 2.1.0 for GitHub Security tab.
          </p>
        </div>
      </div>

    </div>
  );
}
