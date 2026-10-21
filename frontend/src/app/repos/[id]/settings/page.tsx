'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Shield, CheckCircle2, AlertTriangle, Copy, Check, Sparkles, Key } from 'lucide-react';
import { 
  Header, Button, Chip, SkeletonCard, ErrorState, EmptyState 
} from '@/components/ui';
import { fetchApi, Repository, Installation, getAutofixQuota, AutofixQuota, triggerHistoryScan } from '@/lib/api';

export default function RepoSettingsPage() {
  const params = useParams();
  const router = useRouter();
  const repoId = params.id as string;

  const [allRepos, setAllRepos] = useState<Repository[]>([]);
  const [repo, setRepo] = useState<Repository | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form states
  const [scanEnabled, setScanEnabled] = useState(true);
  const [scanOnPr, setScanOnPr] = useState(true);
  const [scanOnPush, setScanOnPush] = useState(true);
  const [scanDrafts, setScanDrafts] = useState(false);
  const [failOn, setFailOn] = useState('high');
  const [ignoreGlobs, setIgnoreGlobs] = useState('');
  const [prCommentEnabled, setPrCommentEnabled] = useState(true);
  const [sarifUploadEnabled, setSarifUploadEnabled] = useState(true);
  const [narrativeEnabled, setNarrativeEnabled] = useState(false);
  const [autofixEnabled, setAutofixEnabled] = useState(false);
  const [autofixDailyQuota, setAutofixDailyQuota] = useState(20);
  const [quotaUsage, setQuotaUsage] = useState<AutofixQuota | null>(null);

  // History Secret Scanning State
  const [historyScanRunning, setHistoryScanRunning] = useState(false);
  const [historyScanProgress, setHistoryScanProgress] = useState<string | null>(null);
  const [historyScanStatus, setHistoryScanStatus] = useState<'idle' | 'running' | 'completed' | 'failed'>('idle');

  // Actions
  const [isSaving, setIsSaving] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [isDeletingData, setIsDeletingData] = useState(false);
  const [feedback, setFeedback] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [copiedBadge, setCopiedBadge] = useState<string | null>(null);

  const handleTriggerHistoryScan = async () => {
    if (!repoId || historyScanRunning) return;
    setHistoryScanRunning(true);
    setHistoryScanStatus('running');
    setHistoryScanProgress('Queuing full git history scan...');
    try {
      const res = await triggerHistoryScan(repoId);
      const scanId = res.scan_id;
      setHistoryScanProgress('Cloning bare history & inspecting commits...');

      const interval = setInterval(async () => {
        try {
          const sRes = await fetchApi(`/api/scan/${scanId}`);
          if (sRes.ok) {
            const sData = await sRes.json();
            const scan = sData.scan;
            if (scan) {
              setHistoryScanProgress(scan.progress ? `Progress: ${scan.progress}` : 'Scanning history...');
              if (scan.status === 'completed') {
                clearInterval(interval);
                setHistoryScanRunning(false);
                setHistoryScanStatus('completed');
                setHistoryScanProgress(`Completed: ${scan.total_issues} secret issue(s) identified.`);
              } else if (scan.status === 'failed') {
                clearInterval(interval);
                setHistoryScanRunning(false);
                setHistoryScanStatus('failed');
                setHistoryScanProgress(`Failed: ${scan.error_message || 'Scan error'}`);
              }
            }
          }
        } catch {
          // Keep polling
        }
      }, 1500);
    } catch (err: any) {
      setHistoryScanRunning(false);
      setHistoryScanStatus('failed');
      setHistoryScanProgress(err.message || 'Failed to trigger history scan');
    }
  };

  const loadData = useCallback(async () => {
    if (!repoId) return;
    try {
      setError(null);

      const reposRes = await fetchApi('/api/repos');
      if (reposRes.status === 401) {
        router.push(`/login?return_to=/repos/${repoId}/settings`);
        return;
      }
      if (reposRes.ok) {
        const data = await reposRes.json();
        setAllRepos(data.repositories || []);
      }

      const res = await fetchApi(`/api/repos/${repoId}`);
      if (res.status === 401) {
        router.push(`/login?return_to=/repos/${repoId}/settings`);
        return;
      }
      if (res.status === 404) {
        setError('Repository not found or has been disconnected.');
        return;
      }
      if (!res.ok) throw new Error('Failed to load repository settings');

      const data = await res.json();
      const r = data.repository;
      setRepo(r);
      setScanEnabled(boolValue(r.scan_enabled, true));
      setScanOnPr(boolValue(r.scan_on_pr, true));
      setScanOnPush(boolValue(r.scan_on_push, true));
      setScanDrafts(boolValue(r.scan_drafts, false));
      setFailOn(r.fail_on || 'high');
      setIgnoreGlobs(r.ignore_globs || '');
      setPrCommentEnabled(boolValue(r.pr_comment_enabled, true));
      setSarifUploadEnabled(boolValue(r.sarif_upload_enabled, true));
      setNarrativeEnabled(boolValue(r.narrative_enabled, false));
      setAutofixEnabled(boolValue(r.autofix_enabled, false));
      setAutofixDailyQuota(r.autofix_daily_quota || 20);

      // Load quota usage
      try {
        const qData = await getAutofixQuota(repoId);
        setQuotaUsage(qData);
      } catch {
        // Non-blocking quota preview
      }
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred');
    } finally {
      setLoading(false);
    }
  }, [repoId, router]);

  function boolValue(v: any, fallback: boolean) {
    if (v === undefined || v === null) return fallback;
    return Boolean(v);
  }

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Save Settings
  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repo || isSaving) return;
    setIsSaving(true);
    setFeedback(null);

    try {
      const res = await fetchApi(`/api/repos/${repo.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scan_enabled: scanEnabled,
          scan_on_pr: scanOnPr,
          scan_on_push: scanOnPush,
          scan_drafts: scanDrafts,
          fail_on: failOn,
          ignore_globs: ignoreGlobs,
          pr_comment_enabled: prCommentEnabled,
          sarif_upload_enabled: sarifUploadEnabled,
          narrative_enabled: narrativeEnabled,
          autofix_enabled: autofixEnabled,
          autofix_daily_quota: autofixDailyQuota
        })
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to update settings');

      setFeedback({ message: 'Repository settings saved successfully.', type: 'success' });
      // Refresh quota
      getAutofixQuota(repo.id).then(setQuotaUsage).catch(() => {});
    } catch (err: any) {
      setFeedback({ message: err.message || 'Failed to update settings.', type: 'error' });
    } finally {
      setIsSaving(false);
    }
  };

  // Copy Badge Markdown / HTML
  const copyBadgeText = (format: 'markdown' | 'html') => {
    if (!repo) return;
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    const badgeUrl = `${origin}/api/repos/${repo.id}/badge.svg`;
    const repoUrl = `${origin}/repos/${repo.id}`;

    const text = format === 'markdown'
      ? `[![CodeVanguard SAST](${badgeUrl})](${repoUrl})`
      : `<a href="${repoUrl}"><img src="${badgeUrl}" alt="CodeVanguard SAST" /></a>`;

    navigator.clipboard.writeText(text);
    setCopiedBadge(format);
    setTimeout(() => setCopiedBadge(null), 2500);
  };

  // Disconnect repo
  const handleDisconnect = async () => {
    if (!repo || isDisconnecting) return;
    if (!window.confirm(`Disconnect "${repo.full_name}" from CodeVanguard?`)) return;

    setIsDisconnecting(true);
    try {
      const res = await fetchApi(`/api/repos/${repo.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to disconnect');
      router.push('/dashboard');
    } catch (err: any) {
      setFeedback({ message: err.message || 'Disconnect failed.', type: 'error' });
      setIsDisconnecting(false);
    }
  };

  // Delete all data
  const handleDeleteData = async () => {
    if (isDeletingData) return;
    if (!window.confirm('WARNING: Permanently delete your personal profile, sessions, and credentials?')) return;

    setIsDeletingData(true);
    try {
      const res = await fetchApi('/api/user/delete-data', { method: 'POST' });
      if (!res.ok) throw new Error('Data purge failed');
      router.push('/login');
    } catch (err: any) {
      setFeedback({ message: err.message || 'Delete data failed.', type: 'error' });
      setIsDeletingData(false);
    }
  };

  return (
    <div className="max-w-[1160px] mx-auto w-full py-4 px-4 sm:px-6 flex flex-col gap-6">
      {/* Header with activeTab="settings" */}
      <Header
        currentRepo={repo || undefined}
        repositories={allRepos}
        activeTab="settings"
      />

      {loading ? (
        <div className="flex flex-col gap-6">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : error ? (
        <ErrorState
          title="Failed to load settings"
          message={error}
          onRetry={loadData}
        />
      ) : !repo ? (
        <EmptyState
          icon={<Shield className="w-7 h-7" />}
          title="Repository not found"
          description="This repository may have been disconnected."
          actionLabel="Return to Dashboard"
          actionHref="/dashboard"
        />
      ) : (
        <form onSubmit={handleSaveSettings} className="flex flex-col gap-6">
          {feedback && (
            <div
              className={`p-4 border-2 border-[#14141A] rounded-[14px] flex items-center gap-3 font-sans text-sm font-bold shadow-[3px_3px_0_#14141A] ${
                feedback.type === 'success' ? 'bg-[#F6FBDD] text-[#14141A]' : 'bg-[#FFD9CC] text-[#14141A]'
              }`}
            >
              {feedback.type === 'success' ? (
                <CheckCircle2 className="w-5 h-5 text-[#14141A] shrink-0" />
              ) : (
                <AlertTriangle className="w-5 h-5 text-[#FF6B3D] shrink-0" />
              )}
              <span>{feedback.message}</span>
            </div>
          )}

          {/* Heading 1: Scan Configuration */}
          <section className="border-2 border-[#14141A] rounded-[18px] bg-white p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-5">
            <div className="flex justify-between items-baseline gap-2 flex-wrap">
              <h2 className="text-xl md:text-2xl font-bold font-sans text-[#14141A] m-0">
                Scan Configuration
              </h2>
              <span className="font-mono text-xs text-[#55555F]">
                Automated SAST & diff rules
              </span>
            </div>

            <div className="flex flex-col gap-4">
              {/* Toggle: scan_enabled */}
              <label className="flex items-center justify-between gap-4 p-3 border-2 border-[#14141A] rounded-[12px] bg-[#F5F4EE] cursor-pointer">
                <div>
                  <span className="font-sans font-bold text-sm text-[#14141A] block">
                    Repository Scanning
                  </span>
                  <span className="font-sans text-xs text-[#55555F]">
                    Globally enable or pause automated static application security scans.
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={scanEnabled}
                  onChange={(e) => setScanEnabled(e.target.checked)}
                  className="w-5 h-5 accent-[#14141A] cursor-pointer"
                />
              </label>

              {/* Toggle: scan_on_pr */}
              <label className="flex items-center justify-between gap-4 p-3 border-2 border-[#14141A] rounded-[12px] bg-[#F5F4EE] cursor-pointer">
                <div>
                  <span className="font-sans font-bold text-sm text-[#14141A] block">
                    Scan on Pull Requests
                  </span>
                  <span className="font-sans text-xs text-[#55555F]">
                    Execute diff-aware static analysis whenever a PR is opened or synchronized.
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={scanOnPr}
                  onChange={(e) => setScanOnPr(e.target.checked)}
                  className="w-5 h-5 accent-[#14141A] cursor-pointer"
                />
              </label>

              {/* Toggle: scan_on_push */}
              <label className="flex items-center justify-between gap-4 p-3 border-2 border-[#14141A] rounded-[12px] bg-[#F5F4EE] cursor-pointer">
                <div>
                  <span className="font-sans font-bold text-sm text-[#14141A] block">
                    Scan on Push (Default Branch Baseline)
                  </span>
                  <span className="font-sans text-xs text-[#55555F]">
                    Run full baseline scans on merges to <strong className="font-mono">{repo.default_branch}</strong> to resolve fixed findings.
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={scanOnPush}
                  onChange={(e) => setScanOnPush(e.target.checked)}
                  className="w-5 h-5 accent-[#14141A] cursor-pointer"
                />
              </label>

              {/* Toggle: scan_drafts */}
              <label className="flex items-center justify-between gap-4 p-3 border-2 border-[#14141A] rounded-[12px] bg-[#F5F4EE] cursor-pointer">
                <div>
                  <span className="font-sans font-bold text-sm text-[#14141A] block">
                    Scan Draft Pull Requests
                  </span>
                  <span className="font-sans text-xs text-[#55555F]">
                    Analyze draft PRs before contributors mark them ready for review.
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={scanDrafts}
                  onChange={(e) => setScanDrafts(e.target.checked)}
                  className="w-5 h-5 accent-[#14141A] cursor-pointer"
                />
              </label>

              {/* Select: fail_on */}
              <div className="flex flex-col gap-1.5">
                <label className="font-sans font-bold text-xs uppercase text-[#14141A]">
                  Fail PR Checks On (Verdict BLOCK threshold)
                </label>
                <select
                  value={failOn}
                  onChange={(e) => setFailOn(e.target.value)}
                  className="w-full max-w-sm px-3 py-2 border-2 border-[#14141A] rounded-[10px] font-sans text-xs bg-white text-[#14141A] focus:outline-none"
                >
                  <option value="critical">Critical findings only</option>
                  <option value="high">Critical or High findings (Default)</option>
                  <option value="medium">Critical, High, or Medium findings</option>
                  <option value="none">Never fail (Informational only)</option>
                </select>
              </div>

              {/* Textarea: ignore_globs */}
              <div className="flex flex-col gap-1.5">
                <div className="flex justify-between items-center gap-2">
                  <label className="font-sans font-bold text-xs uppercase text-[#14141A]">
                    Ignore Glob Patterns (one pattern per line)
                  </label>
                  <span className="font-mono text-[10px] text-[#55555F]">
                    Can also be specified in .codevanguardignore or .codevanguard.yml
                  </span>
                </div>
                <textarea
                  rows={3}
                  value={ignoreGlobs}
                  onChange={(e) => setIgnoreGlobs(e.target.value)}
                  placeholder="tests/**&#10;fixtures/**&#10;*.generated.ts"
                  className="w-full p-2.5 border-2 border-[#14141A] rounded-[10px] font-mono text-xs bg-white text-[#14141A] focus:outline-none"
                />
              </div>

              <div className="pt-2">
                <Button
                  variant="action"
                  type="submit"
                  disabled={isSaving}
                >
                  {isSaving ? 'Saving...' : 'Save Configuration'}
                </Button>
              </div>
            </div>
          </section>

          {/* Heading 2: Integrations & Actions */}
          <section className="border-2 border-[#14141A] rounded-[18px] bg-white p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-5">
            <div className="flex justify-between items-baseline gap-2 flex-wrap">
              <h2 className="text-xl md:text-2xl font-bold font-sans text-[#14141A] m-0">
                Integrations & Actions
              </h2>
              <span className="font-mono text-xs text-[#55555F]">
                GitHub reporting, badge, and tenancy management
              </span>
            </div>

            <div className="flex flex-col gap-4">
              {/* Toggle: pr_comment_enabled */}
              <label className="flex items-center justify-between gap-4 p-3 border-2 border-[#14141A] rounded-[12px] bg-[#F5F4EE] cursor-pointer">
                <div>
                  <span className="font-sans font-bold text-sm text-[#14141A] block">
                    Sticky PR Comment
                  </span>
                  <span className="font-sans text-xs text-[#55555F]">
                    Post and update in-place a single sticky summary comment on pull requests.
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={prCommentEnabled}
                  onChange={(e) => setPrCommentEnabled(e.target.checked)}
                  className="w-5 h-5 accent-[#14141A] cursor-pointer"
                />
              </label>

              {/* Toggle: sarif_upload_enabled */}
              <label className="flex items-center justify-between gap-4 p-3 border-2 border-[#14141A] rounded-[12px] bg-[#F5F4EE] cursor-pointer">
                <div>
                  <span className="font-sans font-bold text-sm text-[#14141A] block">
                    SARIF Upload to GitHub Code Scanning
                  </span>
                  <span className="font-sans text-xs text-[#55555F]">
                    Upload SARIF 2.1.0 reports to populate GitHub's native Security tab.
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={sarifUploadEnabled}
                  onChange={(e) => setSarifUploadEnabled(e.target.checked)}
                  className="w-5 h-5 accent-[#14141A] cursor-pointer"
                />
              </label>

              {/* Toggle: narrative_enabled */}
              <label className="flex items-center justify-between gap-4 p-3 border-2 border-[#14141A] rounded-[12px] bg-[#F5F4EE] cursor-pointer">
                <div>
                  <span className="font-sans font-bold text-sm text-[#14141A] block">
                    AI Reviewer Narrative
                  </span>
                  <span className="font-sans text-xs text-[#55555F]">
                    Synthesize an executive 2-3 sentence summary for reviewers. Facts and integers are strictly verified against deterministic SAST findings.
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={narrativeEnabled}
                  onChange={(e) => setNarrativeEnabled(e.target.checked)}
                  className="w-5 h-5 accent-[#14141A] cursor-pointer"
                />
              </label>

              {/* Toggle: autofix_enabled */}
              <div className="p-4 border-2 border-[#14141A] rounded-[12px] bg-[#F5F4EE] flex flex-col gap-3">
                <label className="flex items-center justify-between gap-4 cursor-pointer">
                  <div>
                    <div className="flex items-center gap-1.5 font-sans font-bold text-sm text-[#14141A]">
                      <Sparkles className="w-4 h-4 text-[#14141A]" />
                      <span>Automated Verified Fixes (Auto-Fix)</span>
                    </div>
                    <span className="font-sans text-xs text-[#55555F]">
                      Generate and re-scan minimal function-scoped patches for detected vulnerabilities before opening pull requests.
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    checked={autofixEnabled}
                    onChange={(e) => setAutofixEnabled(e.target.checked)}
                    className="w-5 h-5 accent-[#14141A] cursor-pointer shrink-0"
                  />
                </label>

                {autofixEnabled && (
                  <div className="flex flex-col gap-3 pt-2 border-t border-[#E2E0D6]">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <div className="flex items-center gap-2">
                        <label className="font-sans font-bold text-xs uppercase text-[#14141A]">
                          Daily Patch Quota
                        </label>
                        <input
                          type="number"
                          min="1"
                          max="100"
                          value={autofixDailyQuota}
                          onChange={(e) => setAutofixDailyQuota(Math.max(1, parseInt(e.target.value) || 20))}
                          className="w-20 px-2.5 py-1 font-mono text-xs border-2 border-[#14141A] rounded-md bg-white text-[#14141A] focus:outline-none"
                        />
                      </div>

                      {quotaUsage && (
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-[#55555F]">
                            Used today: <strong>{quotaUsage.used_today} / {quotaUsage.daily_quota}</strong>
                          </span>
                          <Chip
                            label={`${quotaUsage.remaining} REMAINING`}
                            variant={quotaUsage.remaining > 0 ? 'safe' : 'failed'}
                          />
                        </div>
                      )}
                    </div>

                    <div className="p-3 border-2 border-[#14141A] rounded-[10px] bg-white text-xs font-sans text-[#14141A]">
                      <span className="font-bold block mb-1">⚠️ Auto-Fix Permissions & Privacy Disclosure:</span>
                      <p className="m-0 text-[#55555F] leading-relaxed">
                        Enabling Auto-Fix allows CodeVanguard to extract enclosing function AST nodes and generate candidate patches using your configured LLM provider. Every patch is strictly compiled and re-scanned in an isolated temporary sandbox with Bandit and Semgrep to guarantee zero regressions. Opening PRs requires the GitHub App to have <strong className="font-mono">Contents: write</strong> and <strong className="font-mono">Pull requests: write</strong> permissions. Source code is never persisted to database.
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* Git History Secret Detection Card */}
              <div className="p-4 border-2 border-[#14141A] rounded-[12px] bg-[#F5F4EE] flex flex-col gap-3">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-1.5 font-sans font-bold text-sm text-[#14141A]">
                    <Key className="w-4 h-4 text-[#14141A]" />
                    <span>Git History Secret Detection</span>
                  </div>
                  <Chip
                    label={
                      historyScanStatus === 'running'
                        ? 'SCANNING'
                        : historyScanStatus === 'completed'
                        ? 'COMPLETED'
                        : historyScanStatus === 'failed'
                        ? 'FAILED'
                        : 'IDLE'
                    }
                    variant={
                      historyScanStatus === 'running'
                        ? 'generating'
                        : historyScanStatus === 'completed'
                        ? 'safe'
                        : historyScanStatus === 'failed'
                        ? 'failed'
                        : 'neutral'
                    }
                  />
                </div>
                <p className="font-sans text-xs text-[#55555F] m-0 leading-relaxed">
                  Deeply scan up to 500 commits and 90 days of git history for leaked credentials (including deleted keys). Bare clone uses ephemeral token isolation, strictly enforces a 200MB disk budget, and never persists raw secrets.
                </p>

                {historyScanProgress && (
                  <div className="p-2.5 border-2 border-[#14141A] rounded-[8px] bg-white font-mono text-xs text-[#14141A]">
                    {historyScanProgress}
                  </div>
                )}

                <div className="flex items-center gap-2 flex-wrap pt-1">
                  <Button
                    variant="action"
                    size="sm"
                    type="button"
                    onClick={handleTriggerHistoryScan}
                    disabled={historyScanRunning}
                  >
                    <Key className="w-3.5 h-3.5" />
                    <span>{historyScanRunning ? 'Scanning history...' : 'Run full history scan'}</span>
                  </Button>

                  {historyScanStatus === 'completed' && (
                    <Button
                      variant="secondary"
                      size="sm"
                      type="button"
                      onClick={() => router.push(`/repos/${repoId}/findings?is_secret=true`)}
                    >
                      <span>View Secret Findings</span>
                    </Button>
                  )}
                </div>
              </div>

              {/* Copy Badge Action */}
              <div className="p-4 border-2 border-[#14141A] rounded-[12px] bg-white flex flex-col gap-3">
                <span className="font-sans font-bold text-sm text-[#14141A] block">
                  Security Status Badge
                </span>
                <p className="font-sans text-xs text-[#55555F] m-0">
                  Embed live passing/failing security score status in your repository's README.md.
                </p>
                <div className="flex items-center gap-2 flex-wrap">
                  <Button
                    variant="secondary"
                    size="sm"
                    type="button"
                    onClick={() => copyBadgeText('markdown')}
                  >
                    {copiedBadge === 'markdown' ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedBadge === 'markdown' ? 'Copied Markdown' : 'Copy Badge Markdown'}</span>
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    type="button"
                    onClick={() => copyBadgeText('html')}
                  >
                    {copiedBadge === 'html' ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedBadge === 'html' ? 'Copied HTML' : 'Copy Badge HTML'}</span>
                  </Button>
                </div>
              </div>

              {/* Danger Actions: Disconnect & Delete Data */}
              <div className="flex flex-col sm:flex-row gap-3 pt-3 border-t-2 border-[#E2E0D6]">
                <Button
                  variant="danger"
                  size="sm"
                  type="button"
                  onClick={handleDisconnect}
                  disabled={isDisconnecting}
                >
                  {isDisconnecting ? 'Disconnecting...' : 'Disconnect Repository'}
                </Button>

                <Button
                  variant="danger"
                  size="sm"
                  type="button"
                  onClick={handleDeleteData}
                  disabled={isDeletingData}
                >
                  {isDeletingData ? 'Deleting...' : 'Delete My Data'}
                </Button>
              </div>
            </div>
          </section>
        </form>
      )}
    </div>
  );
}
