'use client';

import React from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { 
  Shield, GitPullRequest, Key, Sparkles, Lock, ArrowRight,
  ExternalLink, CheckCircle2, ShieldCheck, Zap
} from 'lucide-react';

function GithubIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

export default function HomePage() {
  return (
    <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 py-8 md:py-16 flex flex-col gap-16 md:gap-24 w-full">
      
      {/* Hero Section matching Main.dc.html */}
      <section className="flex flex-col lg:flex-row items-center justify-between gap-12 lg:gap-16 w-full">
        {/* Left Column: Pitch and Call to Action */}
        <div className="flex-1 flex flex-col gap-6 max-w-xl text-left">
          <div className="self-start inline-flex items-center gap-2 px-3 py-1 rounded-full border-2 border-[#14141A] bg-[#B8A2FF] font-mono text-xs font-bold text-[#14141A] shadow-[2px_2px_0_#14141A]">
            <span>OPEN-SOURCE SAST · BANDIT + SEMGREP</span>
          </div>

          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-black text-[#14141A] tracking-tight leading-[1.05]">
            Scan. Detect. <br className="hidden sm:inline" />
            <span className="bg-[#D6F25B] px-2 rounded-lg inline-block mt-1">Secure.</span>
          </h1>

          <p className="text-base sm:text-lg text-[#3C3C46] leading-relaxed">
            Connect your GitHub repositories. CodeVanguard checks every pull request, reports only what is new, and proposes security fixes it has already compiler-verified.
          </p>

          {/* Single Connect GitHub CTA */}
          <div className="pt-2 flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <Link
              href="/login"
              className="py-3.5 px-8 border-2 border-[#14141A] rounded-full bg-[#14141A] text-[#F5F4EE] font-bold text-base shadow-[3px_3px_0_#D6F25B] hover:shadow-[1px_1px_0_#D6F25B] hover:translate-x-[2px] hover:translate-y-[2px] transition-all flex items-center justify-center gap-3 cursor-pointer w-full sm:w-auto"
              aria-label="Connect GitHub and begin scanning"
            >
              <GithubIcon className="w-5 h-5 text-[#D6F25B]" />
              <span>Connect GitHub</span>
            </Link>
            <span className="font-mono text-xs text-[#55555F]">
              Free for public &amp; private repositories
            </span>
          </div>
        </div>

        {/* Right Column: Interactive Check Run Simulation Card */}
        <div className="flex-1 w-full max-w-[480px] relative">
          {/* Decorative Sparkle Accent */}
          <div className="absolute -top-6 -right-4 w-12 h-12 text-[#B8A2FF] hidden sm:block pointer-events-none" aria-hidden="true">
            <svg viewBox="0 0 72 72" fill="none" className="w-full h-full">
              <path d="M36 2c3 18 16 31 34 34-18 3-31 16-34 34-3-18-16-31-34-34C20 33 33 20 36 2z" fill="#B8A2FF" stroke="#14141A" strokeWidth="2.5" />
            </svg>
          </div>

          <div className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] p-6 flex flex-col gap-4 w-full">
            <div className="flex items-center justify-between pb-1 border-b border-[#E2E0D6]">
              <div>
                <span className="font-mono text-[11px] font-bold text-[#55555F] block uppercase tracking-wider">CHECK RUN · PR #128</span>
                <span className="text-lg font-black text-[#14141A]">CodeVanguard</span>
              </div>
              <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded border border-[#14141A] bg-[#F5F4EE] text-[#14141A]">
                14 EXISTING HIDDEN
              </span>
            </div>

            <div className="flex flex-col gap-2.5">
              <div className="flex items-center gap-3 p-3 border-2 border-[#14141A] rounded-xl bg-white">
                <span className="font-mono text-[11px] font-bold px-2 py-0.5 rounded border border-[#14141A] bg-[#FF6B3D] text-white">
                  CRITICAL
                </span>
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-xs text-[#14141A] truncate">subprocess with shell=True</div>
                  <div className="font-mono text-[10px] text-[#55555F]">api/export.py:42</div>
                </div>
              </div>

              <div className="flex items-center gap-3 p-3 border-2 border-[#14141A] rounded-xl bg-white">
                <span className="font-mono text-[11px] font-bold px-2 py-0.5 rounded border border-[#14141A] bg-[#FFC93C] text-[#14141A]">
                  HIGH
                </span>
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-xs text-[#14141A] truncate">SQL built from string concat</div>
                  <div className="font-mono text-[10px] text-[#55555F]">db/orders.py:118</div>
                </div>
              </div>
            </div>

            <Link
              href="/login"
              className="py-2.5 px-4 border-2 border-[#14141A] rounded-full bg-[#D6F25B] text-[#14141A] font-bold text-xs text-center shadow-[2px_2px_0_#14141A] hover:translate-x-[1px] hover:translate-y-[1px] transition-all flex items-center justify-center gap-1.5"
            >
              <span>Open verified fix PR</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      </section>

      {/* Feature Showcase Grid ("What it does") */}
      <section className="flex flex-col gap-8 w-full">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b-2 border-[#14141A] pb-4">
          <div className="flex items-center gap-3">
            <h2 className="text-2xl sm:text-3xl font-black text-[#14141A] bg-[#D6F25B] px-3 py-1 rounded-md">
              What it does
            </h2>
            <span className="text-xs sm:text-sm font-bold text-[#55555F]">
              Four pillars traditional SAST tools skip.
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 w-full">
          {/* Card 1: Diff-Aware Scans */}
          <article className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] p-6 flex flex-col justify-between gap-4">
            <div className="flex flex-col gap-2.5">
              <span className="w-10 h-10 rounded-xl bg-[#D6F25B] border-2 border-[#14141A] flex items-center justify-center text-[#14141A]">
                <GitPullRequest className="w-5 h-5" />
              </span>
              <h3 className="text-lg font-black text-[#14141A]">Diff-aware PR scans</h3>
              <p className="text-xs text-[#55555F] leading-relaxed">
                Only new findings land on your pull request. We benchmark against your default branch baseline so existing legacy code never blocks your merge.
              </p>
            </div>
            <span className="font-mono text-[10px] text-[#14141A] font-bold">Zero alert fatigue</span>
          </article>

          {/* Card 2: Verified Auto-Fix */}
          <article className="border-2 border-[#14141A] rounded-[18px] bg-[#14141A] text-[#F5F4EE] shadow-[5px_5px_0_#D6F25B] p-6 flex flex-col justify-between gap-4">
            <div className="flex flex-col gap-2.5">
              <span className="w-10 h-10 rounded-xl bg-[#B8A2FF] border-2 border-[#F5F4EE] flex items-center justify-center text-[#14141A]">
                <Sparkles className="w-5 h-5" />
              </span>
              <h3 className="text-lg font-black text-[#F5F4EE]">Verified auto-fix</h3>
              <p className="text-xs text-[#D0CFD8] leading-relaxed">
                An LLM drafts minimal patches. We compile and re-scan the candidate in an isolated sandbox before offering a pull request.
              </p>
            </div>
            <span className="font-mono text-[10px] text-[#D6F25B] font-bold">100% verified patches</span>
          </article>

          {/* Card 3: History Secret Scan */}
          <article className="border-2 border-[#14141A] rounded-[18px] bg-[#14141A] text-[#F5F4EE] shadow-[5px_5px_0_#D6F25B] p-6 flex flex-col justify-between gap-4">
            <div className="flex flex-col gap-2.5">
              <span className="w-10 h-10 rounded-xl bg-[#FF6B3D] border-2 border-[#F5F4EE] flex items-center justify-center text-white">
                <Key className="w-5 h-5" />
              </span>
              <h3 className="text-lg font-black text-[#F5F4EE]">History secret scan</h3>
              <p className="text-xs text-[#D0CFD8] leading-relaxed">
                A key deleted from HEAD is still in git history. We bare-clone with depth bounds, stream git diffs, and guide immediate credential rotation.
              </p>
            </div>
            <span className="font-mono text-[10px] text-[#D6F25B] font-bold">Rotate first workflow</span>
          </article>

          {/* Card 4: Local & Offline Speed */}
          <article className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] p-6 flex flex-col justify-between gap-4">
            <div className="flex flex-col gap-2.5">
              <span className="w-10 h-10 rounded-xl bg-[#D6F25B] border-2 border-[#14141A] flex items-center justify-center text-[#14141A]">
                <Zap className="w-5 h-5" />
              </span>
              <h3 className="text-lg font-black text-[#14141A]">Local offline speed</h3>
              <p className="text-xs text-[#55555F] leading-relaxed">
                Executes Bandit AST parsing and local Semgrep rules without calling external SaaS registries. Scans return in milliseconds.
              </p>
            </div>
            <span className="font-mono text-[10px] text-[#14141A] font-bold">OASIS SARIF 2.1.0</span>
          </article>
        </div>
      </section>

      {/* Real Application Visuals Showcase */}
      <section className="flex flex-col gap-6 w-full">
        <div className="flex items-center justify-between border-b-2 border-[#14141A] pb-3">
          <h2 className="text-2xl font-black text-[#14141A]">Built for Engineering Velocity</h2>
          <span className="font-mono text-xs text-[#55555F]">Real dashboard previews</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full">
          {/* Dashboard Preview Card */}
          <div className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] overflow-hidden flex flex-col">
            <div className="p-4 bg-[#F5F4EE] border-b-2 border-[#14141A] flex items-center justify-between">
              <span className="font-mono text-xs font-bold text-[#14141A]">Repository Dashboard</span>
              <span className="font-mono text-[11px] text-[#55555F]">Overview &amp; Baseline Trend</span>
            </div>
            <div className="p-4 flex-1 flex items-center justify-center bg-slate-50">
              <img
                src="/design/dashboard.png"
                alt="CodeVanguard Repository Dashboard"
                className="w-full h-auto rounded-lg border-2 border-[#14141A] shadow-[2px_2px_0_#14141A]"
                loading="lazy"
              />
            </div>
          </div>

          {/* Landing / Intake Preview Card */}
          <div className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] overflow-hidden flex flex-col">
            <div className="p-4 bg-[#F5F4EE] border-b-2 border-[#14141A] flex items-center justify-between">
              <span className="font-mono text-xs font-bold text-[#14141A]">Interactive Intake Terminal</span>
              <span className="font-mono text-[11px] text-[#55555F]">Live Scan Feedback</span>
            </div>
            <div className="p-4 flex-1 flex items-center justify-center bg-slate-50">
              <img
                src="/design/landing.png"
                alt="CodeVanguard Landing & Intake Terminal"
                className="w-full h-auto rounded-lg border-2 border-[#14141A] shadow-[2px_2px_0_#14141A]"
                loading="lazy"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Ephemeral Workspace & Privacy Guarantee matching Main.dc.html */}
      <section className="border-2 border-[#14141A] rounded-[18px] bg-[#B8A2FF] shadow-[5px_5px_0_#14141A] p-8 md:p-12 flex flex-col md:flex-row items-start md:items-center justify-between gap-8 w-full">
        <div className="flex flex-col gap-3 max-w-xl">
          <span className="font-mono text-xs font-bold px-2.5 py-1 rounded border-2 border-[#14141A] bg-white text-[#14141A] self-start">
            DATA GUARANTEE
          </span>
          <h2 className="text-3xl md:text-4xl font-black text-[#14141A] tracking-tight leading-tight">
            Your source code is never stored.
          </h2>
          <p className="text-sm md:text-base text-[#14141A] leading-relaxed">
            Repositories are analyzed in ephemeral isolated workspaces purged immediately in a mandatory <code className="bg-white/60 px-1 py-0.5 rounded font-mono text-xs font-bold">finally</code> block upon scan completion. We retain only vulnerability metadata and short contextual snippets.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-3 w-full md:w-auto">
          <Link
            href="/privacy"
            className="py-3 px-6 border-2 border-[#14141A] rounded-full bg-[#14141A] text-[#F5F4EE] font-bold text-xs sm:text-sm shadow-[3px_3px_0_#D6F25B] hover:translate-x-[1px] hover:translate-y-[1px] transition-all text-center w-full sm:w-auto"
          >
            Read Privacy Statement &rarr;
          </Link>
          <Link
            href="/status"
            className="py-3 px-6 border-2 border-[#14141A] rounded-full bg-white text-[#14141A] font-bold text-xs sm:text-sm shadow-[3px_3px_0_#14141A] hover:translate-x-[1px] hover:translate-y-[1px] transition-all text-center w-full sm:w-auto"
          >
            System Status
          </Link>
        </div>
      </section>

    </div>
  );
}
