'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { ShieldCheck, Trash2, ArrowLeft, Lock, HardDrive, EyeOff, Server, AlertTriangle, KeyRound, Cpu } from 'lucide-react';
import { fetchApi } from '@/lib/api';

export default function PrivacyPolicyPage() {
  const [deleting, setDeleting] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleDeleteData = async () => {
    if (!window.confirm("Are you sure you want to delete your CodeVanguard personal data? This permanently purges your personal scans, installation memberships, and stored access tokens.")) {
      return;
    }

    setDeleting(true);
    setDeleteError(null);
    setDeleteMessage(null);

    try {
      const res = await fetchApi('/api/user/delete-data', {
        method: 'POST'
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to purge data.");
      }
      setDeleteMessage("Your personal data and stored tokens have been permanently purged.");
    } catch (err: any) {
      setDeleteError(err.message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto py-8 px-4 flex flex-col gap-8">
      {/* Top navigation */}
      <div className="flex items-center justify-between">
        <Link
          href="/"
          className="inline-flex items-center gap-2 font-mono text-xs font-bold text-[#14141A] hover:underline"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Home
        </Link>
        <Link
          href="/status"
          className="inline-flex items-center gap-2 font-mono text-xs font-bold text-[#14141A] hover:underline"
        >
          View System Status &rarr;
        </Link>
      </div>

      {/* Hero Banner matching design */}
      <div className="border-2 border-[#14141A] rounded-[18px] bg-[#B8A2FF] shadow-[5px_5px_0_#14141A] p-8 md:p-10 flex flex-col gap-4">
        <span className="font-mono text-xs font-bold px-2.5 py-1 rounded border-2 border-[#14141A] bg-white text-[#14141A] self-start">
          DATA GUARANTEE
        </span>
        <h1 className="text-4xl md:text-5xl font-black text-[#14141A] tracking-tight leading-tight">
          Your source code is never stored.
        </h1>
        <p className="text-lg md:text-xl text-[#14141A] leading-relaxed max-w-2xl font-medium">
          Repositories are scanned in an ephemeral workspace destroyed immediately after the run. We store only metadata and short contextual snippets (max ~7 lines).
        </p>
      </div>

      {/* Core Privacy Pillars */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] p-6 flex flex-col gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#D6F25B] border-2 border-[#14141A] flex items-center justify-center">
            <HardDrive className="w-5 h-5 text-[#14141A]" />
          </div>
          <h2 className="text-xl font-black text-[#14141A]">Ephemeral Workspaces</h2>
          <p className="text-sm text-[#55555F] leading-relaxed">
            When a scan executes, code is streamed into a temporary isolated directory. As soon as the Bandit and Semgrep scans finish, the entire directory is purged in a mandatory <code className="bg-[#F5F4EE] px-1 py-0.5 rounded border border-[#14141A] font-mono text-xs">finally</code> block.
          </p>
        </div>

        <div className="border-2 border-[#14141A] rounded-[18px] bg-[#14141A] text-[#F5F4EE] shadow-[5px_5px_0_#D6F25B] p-6 flex flex-col gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#FF6B3D] border-2 border-[#F5F4EE] flex items-center justify-center">
            <Lock className="w-5 h-5 text-white" />
          </div>
          <h2 className="text-xl font-black text-[#F5F4EE]">Token Encryption &amp; Redaction</h2>
          <p className="text-sm text-[#D0CFD8] leading-relaxed">
            GitHub App and OAuth tokens are encrypted at rest using Fernet symmetric encryption (<code className="font-mono text-xs text-[#D6F25B]">TOKEN_ENCRYPTION_KEY</code>). All application loggers run active filters that strip GitHub token prefixes before write.
          </p>
        </div>

        <div className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] p-6 flex flex-col gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#FFC93C] border-2 border-[#14141A] flex items-center justify-center">
            <EyeOff className="w-5 h-5 text-[#14141A]" />
          </div>
          <h2 className="text-xl font-black text-[#14141A]">Metadata &amp; Fingerprints Only</h2>
          <p className="text-sm text-[#55555F] leading-relaxed">
            Findings retain only file paths, line numbers, rule descriptions, and normalized SHA-256 fingerprints to track recurring vulnerabilities. Full repo contents are never saved to database tables or object stores.
          </p>
        </div>

        <div className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] p-6 flex flex-col gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#D6F25B] border-2 border-[#14141A] flex items-center justify-center">
            <Server className="w-5 h-5 text-[#14141A]" />
          </div>
          <h2 className="text-xl font-black text-[#14141A]">Multi-Tenant Isolation</h2>
          <p className="text-sm text-[#55555F] leading-relaxed">
            Installation members see only their own repositories and scans. Unauthenticated users cannot query private scans, read findings, or trigger background jobs on installed repos.
          </p>
        </div>

        <div className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] p-6 flex flex-col gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#FF6B3D] border-2 border-[#14141A] flex items-center justify-center">
            <KeyRound className="w-5 h-5 text-white" />
          </div>
          <h2 className="text-xl font-black text-[#14141A]">Safe Secret Detection</h2>
          <p className="text-sm text-[#55555F] leading-relaxed">
            Raw detected secrets are never stored. Only a masked preview (<code className="bg-[#F5F4EE] px-1 py-0.5 rounded border border-[#14141A] font-mono text-xs">first 4 + last 2 chars</code>) and a salted SHA-256 fingerprint are recorded. CodeVanguard never validates secrets by calling 3rd-party provider APIs.
          </p>
        </div>

        <div className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] p-6 flex flex-col gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#B8A2FF] border-2 border-[#14141A] flex items-center justify-center">
            <Cpu className="w-5 h-5 text-[#14141A]" />
          </div>
          <h2 className="text-xl font-black text-[#14141A]">Bounded Auto-Fix Context</h2>
          <p className="text-sm text-[#55555F] leading-relaxed">
            Auto-Fix is strictly per-repo opt-in. We never send whole repos to LLMs. Tree-sitter extracts only the target function and its immediate imports, and all tokens are actively redacted before sending. Ollama is supported for 100% on-premises execution.
          </p>
        </div>
      </div>

      {/* Self-service data deletion */}
      <div className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] p-6 md:p-8 flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#FFD9CC] border-2 border-[#14141A] flex items-center justify-center">
            <Trash2 className="w-5 h-5 text-[#FF6B3D]" />
          </div>
          <div>
            <h2 className="text-xl font-black text-[#14141A]">Self-Service Data Purge</h2>
            <p className="text-xs text-[#55555F]">Right to be forgotten &amp; account cleanup</p>
          </div>
        </div>

        <p className="text-sm text-[#55555F] leading-relaxed">
          If you are signed in, you can permanently delete all your personal scans, installation links, and stored encrypted tokens with a single click.
        </p>

        {deleteMessage && (
          <div className="p-3 bg-[#DDF58A] border-2 border-[#14141A] rounded-xl font-mono text-xs text-[#14141A] font-bold">
            {deleteMessage}
          </div>
        )}

        {deleteError && (
          <div className="p-3 bg-[#FFD9CC] border-2 border-[#14141A] rounded-xl font-mono text-xs text-[#14141A] font-bold">
            {deleteError}
          </div>
        )}

        <div className="pt-2">
          <button
            onClick={handleDeleteData}
            disabled={deleting}
            className="py-2.5 px-5 border-2 border-[#14141A] rounded-full bg-[#FF6B3D] text-white font-bold text-sm shadow-[3px_3px_0_#14141A] hover:shadow-[1px_1px_0_#14141A] hover:translate-x-[2px] hover:translate-y-[2px] transition-all cursor-pointer disabled:opacity-50"
          >
            {deleting ? "Purging data..." : "Permanently Purge My Data"}
          </button>
        </div>
      </div>
    </div>
  );
}
