'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { 
  Shield, Search, X, CheckCircle, XCircle, ExternalLink, 
  AlertTriangle, Filter, ChevronRight, Sparkles, Download, GitPullRequest, Copy, Check, Key 
} from 'lucide-react';
import { 
  Header, Chip, Button, SkeletonCard, ErrorState, EmptyState, CodeDiff 
} from '@/components/ui';
import { 
  fetchApi, Repository, FixAttempt, generateFindingFix, 
  getLatestFindingFix, createFindingFixPR 
} from '@/lib/api';

interface Finding {
  id: string;
  repo_id: string;
  fingerprint: string;
  rule_id: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  title: string;
  filepath: string;
  line_number: number;
  first_seen_commit: string;
  first_seen_at: string;
  last_seen_at: string;
  introduced_by_pr?: number | null;
  state: 'open' | 'fixed' | 'suppressed' | 'false_positive';
  suppressed_by?: number | null;
  suppressed_at?: string | null;
  reason?: string | null;
  suppressed_by_username?: string | null;
  code_snippet?: string;
  fix_title?: string;
  fix_description?: string;
  fix_before?: string;
  fix_after?: string;
  doc_url?: string;
  scanner?: string;
  masked_secret?: string;
  detector?: string;
  commit_sha?: string;
  commit_date?: string;
  still_in_head?: boolean;
  is_secret?: boolean;
}

export default function RepoFindingsPage() {
  const params = useParams();
  const router = useRouter();
  const repoId = params.id as string;

  const [allRepos, setAllRepos] = useState<Repository[]>([]);
  const [repo, setRepo] = useState<Repository | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [stateFilter, setStateFilter] = useState<string>('all');
  const [scannerFilter, setScannerFilter] = useState<string>('all');
  const [secretOnlyFilter, setSecretOnlyFilter] = useState<boolean>(false);
  const [introducedByPr, setIntroducedByPr] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const perPage = 15;

  // Selected finding for side panel
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [isSuppressModalOpen, setIsSuppressModalOpen] = useState(false);
  const [suppressState, setSuppressState] = useState<'suppressed' | 'false_positive'>('suppressed');
  const [suppressReason, setSuppressReason] = useState<string>('');
  const [isSubmittingAction, setIsSubmittingAction] = useState(false);

  // Auto-Fix state
  const [fixAttempt, setFixAttempt] = useState<FixAttempt | null>(null);
  const [loadingFix, setLoadingFix] = useState<boolean>(false);
  const [generatingFix, setGeneratingFix] = useState<boolean>(false);
  const [creatingFixPR, setCreatingFixPR] = useState<boolean>(false);
  const [fixError, setFixError] = useState<string | null>(null);
  const [patchCopied, setPatchCopied] = useState<boolean>(false);

  // Load latest fix attempt when selecting a finding
  useEffect(() => {
    if (!selectedFinding || !repoId) {
      setFixAttempt(null);
      setFixError(null);
      return;
    }
    let isCancelled = false;
    setLoadingFix(true);
    setFixError(null);
    getLatestFindingFix(repoId, selectedFinding.id)
      .then((res) => {
        if (!isCancelled) {
          setFixAttempt(res.fix_attempt);
        }
      })
      .catch((err) => {
        if (!isCancelled) {
          setFixError(err.message || 'Failed to check auto-fix history');
        }
      })
      .finally(() => {
        if (!isCancelled) setLoadingFix(false);
      });

    return () => {
      isCancelled = true;
    };
  }, [selectedFinding, repoId]);

  const handleGenerateFix = async () => {
    if (!selectedFinding || !repoId || generatingFix) return;
    setGeneratingFix(true);
    setFixError(null);
    try {
      const res = await generateFindingFix(repoId, selectedFinding.id);
      setFixAttempt(res.fix_attempt);
    } catch (err: any) {
      setFixError(err.message || 'Failed to generate auto-fix');
    } finally {
      setGeneratingFix(false);
    }
  };

  const handleCreateFixPR = async () => {
    if (!selectedFinding || !repoId || !fixAttempt || creatingFixPR) return;
    setCreatingFixPR(true);
    setFixError(null);
    try {
      const res = await createFindingFixPR(repoId, selectedFinding.id);
      setFixAttempt((prev) => prev ? {
        ...prev,
        status: 'pr_opened',
        pr_number: res.pr_number,
        pr_url: res.pr_url,
        branch_name: res.branch_name
      } : null);
    } catch (err: any) {
      setFixError(err.message || 'Failed to open fix PR on GitHub');
    } finally {
      setCreatingFixPR(false);
    }
  };

  const handleDownloadFixedFile = () => {
    if (!fixAttempt || !fixAttempt.patch_code) return;
    const blob = new Blob([fixAttempt.patch_code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const filename = fixAttempt.target_file ? fixAttempt.target_file.split('/').pop() || 'fixed_file.py' : 'fixed_file.py';
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleCopyPatch = () => {
    if (!fixAttempt || !fixAttempt.diff) return;
    navigator.clipboard.writeText(fixAttempt.diff);
    setPatchCopied(true);
    setTimeout(() => setPatchCopied(false), 2000);
  };

  const loadData = useCallback(async () => {
    if (!repoId) return;
    try {
      setError(null);

      // Load all repositories for RepoSwitcher
      const reposRes = await fetchApi('/api/repos');
      if (reposRes.status === 401) {
        router.push(`/login?return_to=/repos/${repoId}/findings`);
        return;
      }
      if (reposRes.ok) {
        const data = await reposRes.json();
        setAllRepos(data.repositories || []);
      }

      // Load current repo
      const repoRes = await fetchApi(`/api/repos/${repoId}`);
      if (repoRes.status === 401) {
        router.push(`/login?return_to=/repos/${repoId}/findings`);
        return;
      }
      if (repoRes.status === 404) {
        setError('Repository not found or disconnected.');
        return;
      }
      if (!repoRes.ok) {
        throw new Error('Failed to load repository');
      }
      const repoData = await repoRes.json();
      setRepo(repoData.repository);

      // Load findings with query params
      const qParams = new URLSearchParams();
      if (severityFilter !== 'all') qParams.set('severity', severityFilter);
      if (stateFilter !== 'all') qParams.set('state', stateFilter);
      if (scannerFilter !== 'all') qParams.set('scanner', scannerFilter);
      if (secretOnlyFilter) qParams.set('is_secret', 'true');
      if (introducedByPr) qParams.set('introduced_by_pr', '1');
      if (searchQuery.trim()) qParams.set('search', searchQuery.trim());
      qParams.set('page', String(currentPage));
      qParams.set('per_page', String(perPage));

      const findingsRes = await fetchApi(`/api/repos/${repoId}/findings?${qParams.toString()}`);
      if (!findingsRes.ok) throw new Error('Failed to load findings');
      const findingsData = await findingsRes.json();

      setFindings(findingsData.findings || []);
      setTotalCount(findingsData.total_count || 0);
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred');
    } finally {
      setLoading(false);
    }
  }, [repoId, severityFilter, stateFilter, scannerFilter, secretOnlyFilter, introducedByPr, searchQuery, currentPage, router]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle Suppress Action
  const handleSuppress = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFinding || !suppressReason.trim()) return;

    setIsSubmittingAction(true);
    try {
      const res = await fetchApi(`/api/repos/${repoId}/findings/${selectedFinding.id}/suppress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state: suppressState, reason: suppressReason.trim() })
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || 'Failed to suppress finding');
      }

      setIsSuppressModalOpen(false);
      setSuppressReason('');
      // Reload findings
      await loadData();
      // Update selected finding state
      setSelectedFinding(prev => prev ? { ...prev, state: suppressState, reason: suppressReason } : null);
    } catch (err: any) {
      alert(err.message || 'Failed to suppress finding');
    } finally {
      setIsSubmittingAction(false);
    }
  };

  // Handle Unsuppress Action
  const handleUnsuppress = async () => {
    if (!selectedFinding) return;
    setIsSubmittingAction(true);
    try {
      const res = await fetchApi(`/api/repos/${repoId}/findings/${selectedFinding.id}/unsuppress`, {
        method: 'POST'
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || 'Failed to restore finding');
      }

      await loadData();
      setSelectedFinding(prev => prev ? { ...prev, state: 'open', reason: null } : null);
    } catch (err: any) {
      alert(err.message || 'Failed to restore finding');
    } finally {
      setIsSubmittingAction(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(totalCount / perPage));

  return (
    <div className="max-w-[1160px] mx-auto w-full py-4 px-4 sm:px-6 flex flex-col gap-6">
      {/* Header with activeTab="findings" */}
      <Header
        currentRepo={repo || undefined}
        repositories={allRepos}
        activeTab="findings"
      />

      {loading && !selectedFinding ? (
        <div className="flex flex-col gap-4">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : error ? (
        <ErrorState
          title="Failed to load repository findings"
          message={error}
          onRetry={loadData}
        />
      ) : (
        <section className="border-2 border-[#14141A] rounded-[18px] bg-white p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-5">
          <div className="flex justify-between items-center gap-3 flex-wrap">
            <h2 className="text-xl md:text-2xl font-bold font-sans text-[#14141A] m-0">
              Findings Registry
            </h2>
            <span className="font-mono text-xs text-[#55555F]">
              Showing {findings.length} of {totalCount} findings
            </span>
          </div>

          {/* Filters Bar */}
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {/* Severity filter */}
              <div className="flex flex-wrap gap-1 bg-[#F5F4EE] p-1 rounded-full border-2 border-[#14141A] text-xs font-bold font-sans">
                {(['all', 'critical', 'high', 'medium', 'low'] as const).map((sev) => (
                  <button
                    key={sev}
                    onClick={() => { setSeverityFilter(sev); setCurrentPage(1); }}
                    className={`px-3 py-1 rounded-full uppercase transition-all cursor-pointer ${
                      severityFilter === sev
                        ? 'bg-[#14141A] text-[#F5F4EE]'
                        : 'text-[#14141A] hover:bg-[#E2E0D6]'
                    }`}
                  >
                    {sev}
                  </button>
                ))}
              </div>

              {/* State filter */}
              <select
                value={stateFilter}
                onChange={(e) => { setStateFilter(e.target.value); setCurrentPage(1); }}
                className="px-3 py-1.5 border-2 border-[#14141A] rounded-full font-sans text-xs font-bold bg-white text-[#14141A] focus:outline-none"
              >
                <option value="all">All States</option>
                <option value="open">Open</option>
                <option value="fixed">Fixed</option>
                <option value="suppressed">Suppressed</option>
                <option value="false_positive">False Positive</option>
              </select>

              {/* Scanner filter */}
              <select
                value={scannerFilter}
                onChange={(e) => { setScannerFilter(e.target.value); setCurrentPage(1); }}
                className="px-3 py-1.5 border-2 border-[#14141A] rounded-full font-sans text-xs font-bold bg-white text-[#14141A] focus:outline-none"
              >
                <option value="all">All Scanners</option>
                <option value="bandit">Bandit AST</option>
                <option value="semgrep">Semgrep Rules</option>
                <option value="secret">Secret Scanner</option>
              </select>

              {/* Dedicated Secrets Filter */}
              <button
                type="button"
                onClick={() => { setSecretOnlyFilter(prev => !prev); setCurrentPage(1); }}
                className={`px-3 py-1.5 rounded-full border-2 border-[#14141A] font-sans text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                  secretOnlyFilter
                    ? 'bg-[#E03E3E] text-white shadow-[2px_2px_0_#14141A]'
                    : 'bg-[#F5F4EE] text-[#14141A] hover:bg-[#E2E0D6]'
                }`}
              >
                <Key className="w-3.5 h-3.5" />
                <span>Secrets</span>
              </button>

              {/* Introduced by PR Checkbox */}
              <label className="inline-flex items-center gap-1.5 px-3 py-1.5 border-2 border-[#14141A] rounded-full font-sans text-xs font-bold bg-[#F5F4EE] cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={introducedByPr}
                  onChange={(e) => { setIntroducedByPr(e.target.checked); setCurrentPage(1); }}
                  className="rounded accent-[#14141A]"
                />
                <span>Introduced by PR</span>
              </label>
            </div>

            {/* Search Input */}
            <div className="relative w-full max-w-md">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-[#55555F] pointer-events-none">
                <Search className="w-4 h-4" />
              </span>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
                placeholder="Search findings by rule, title or path..."
                className="w-full pl-9 pr-3 py-2 border-2 border-[#14141A] rounded-full font-sans text-xs bg-white text-[#14141A] focus:outline-none placeholder:text-[#888899]"
              />
            </div>
          </div>

          {/* Table */}
          {findings.length === 0 ? (
            <div className="p-8 text-center bg-[#F5F4EE] border-2 border-[#14141A] rounded-[14px]">
              <p className="font-sans font-bold text-sm text-[#55555F] m-0">
                Zero findings match the selected filter criteria.
              </p>
            </div>
          ) : (
            <div className="flex flex-col divide-y-2 divide-[#E2E0D6] border-2 border-[#14141A] rounded-[14px] overflow-hidden">
              {findings.map((finding) => {
                // Rule: state chip ONLY when it is not 'open'
                const showStateChip = finding.state !== 'open';
                const stateVariant =
                  finding.state === 'fixed'
                    ? 'safe'
                    : finding.state === 'suppressed'
                    ? 'neutral'
                    : 'attention';

                const isSecret = Boolean(finding.is_secret || finding.masked_secret || finding.scanner === 'secret' || (finding.rule_id && finding.rule_id.startsWith('SECRET_')));
                const secretChipLabel = finding.still_in_head ? 'HEAD' : 'HISTORY ONLY';
                const secretChipVariant = finding.still_in_head ? 'critical' : 'high';

                return (
                  <div
                    key={finding.id}
                    onClick={() => setSelectedFinding(finding)}
                    className="p-3.5 flex items-center justify-between gap-3 flex-wrap hover:bg-[#F5F4EE] cursor-pointer transition-colors bg-white select-none"
                  >
                    <div className="flex items-center gap-3 flex-wrap min-w-[200px]">
                      {isSecret ? (
                        <Chip
                          label={secretChipLabel}
                          variant={secretChipVariant}
                        />
                      ) : (
                        <Chip
                          label={finding.severity.toUpperCase()}
                          variant={finding.severity}
                        />
                      )}

                      <div className="text-left flex flex-col gap-0.5">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-sans font-bold text-sm text-[#14141A]">
                            {finding.detector || finding.title}
                          </span>
                          {isSecret && finding.masked_secret && (
                            <code className="font-mono text-xs font-bold px-1.5 py-0.5 bg-[#F5F4EE] border border-[#14141A] rounded text-[#E03E3E]">
                              {finding.masked_secret}
                            </code>
                          )}
                        </div>
                        <div className="font-mono text-xs text-[#55555F] break-all">
                          {finding.filepath}:{finding.line_number}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-wrap">
                      {isSecret && finding.commit_sha && (
                        <a
                          href={repo ? `https://github.com/${repo.full_name}/commit/${finding.commit_sha}` : '#'}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 font-mono text-xs text-[#14141A] hover:underline bg-[#F5F4EE] px-2 py-0.5 rounded border border-[#14141A]"
                          title="View commit on GitHub"
                        >
                          <span>{finding.commit_sha.slice(0, 7)}</span>
                          <ExternalLink className="w-3 h-3 text-[#55555F]" />
                        </a>
                      )}
                      {showStateChip && (
                        <Chip
                          label={finding.state.replace('_', ' ').toUpperCase()}
                          variant={stateVariant}
                        />
                      )}
                      <ChevronRight className="w-4 h-4 text-[#55555F]" />
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex justify-between items-center gap-3 pt-2 flex-wrap">
              <span className="font-mono text-xs text-[#55555F]">
                Page {currentPage} of {totalPages}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={currentPage === 1}
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={currentPage >= totalPages}
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </section>
      )}

      {/* Side Panel Drawer for Selected Finding */}
      {selectedFinding && (() => {
        const isSelectedSecret = Boolean(
          selectedFinding.is_secret ||
          selectedFinding.masked_secret ||
          selectedFinding.scanner === 'secret' ||
          (selectedFinding.rule_id && selectedFinding.rule_id.startsWith('SECRET_'))
        );
        const drawerChipLabel = isSelectedSecret
          ? (selectedFinding.still_in_head ? 'HEAD' : 'HISTORY ONLY')
          : selectedFinding.severity.toUpperCase();
        const drawerChipVariant = isSelectedSecret
          ? (selectedFinding.still_in_head ? 'critical' : 'high')
          : selectedFinding.severity;

        return (
          <div className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-xs">
            <div className="w-full max-w-lg bg-white h-full border-l-4 border-[#14141A] p-6 shadow-2xl flex flex-col gap-5 overflow-y-auto">
              {/* Drawer Header */}
              <div className="flex justify-between items-start gap-3">
                <div className="flex items-center gap-2.5 flex-wrap">
                  <Chip
                    label={drawerChipLabel}
                    variant={drawerChipVariant}
                  />
                  {selectedFinding.state !== 'open' && (
                    <Chip
                      label={selectedFinding.state.replace('_', ' ').toUpperCase()}
                      variant={selectedFinding.state === 'fixed' ? 'safe' : 'neutral'}
                    />
                  )}
                </div>
                <button
                  onClick={() => setSelectedFinding(null)}
                  className="p-1 rounded-full border-2 border-[#14141A] hover:bg-[#F5F4EE] transition-colors"
                  aria-label="Close details"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Title & Metadata */}
              <div className="flex flex-col gap-1">
                <h3 className="font-sans text-xl font-bold text-[#14141A] m-0">
                  {selectedFinding.detector || selectedFinding.title}
                </h3>
                {isSelectedSecret && selectedFinding.masked_secret && (
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="font-sans text-xs text-[#55555F]">Exposed preview:</span>
                    <code className="font-mono text-xs font-bold px-2 py-0.5 bg-[#FFF5F5] border border-[#14141A] rounded text-[#E03E3E]">
                      {selectedFinding.masked_secret}
                    </code>
                  </div>
                )}
                <span className="font-mono text-xs text-[#55555F]">
                  {selectedFinding.filepath}:{selectedFinding.line_number}
                </span>
                <div className="font-mono text-[11px] text-[#888899] mt-1 flex items-center gap-2 flex-wrap">
                  <span>Rule ID: {selectedFinding.rule_id}</span>
                  {selectedFinding.commit_sha && (
                    <span>· Commit: {selectedFinding.commit_sha.slice(0, 7)}</span>
                  )}
                </div>
              </div>

              {/* 'Rotate First' Checklist for Secrets */}
              {isSelectedSecret && (
                <div className="flex flex-col gap-3 p-4 border-2 border-[#14141A] rounded-[14px] bg-[#FFF5F5] shadow-[3px_3px_0_#14141A]">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-[#E03E3E]" />
                    <span className="font-sans font-bold text-sm text-[#14141A] uppercase tracking-wide">
                      Rotate First Checklist
                    </span>
                  </div>
                  <p className="font-sans text-xs text-[#55555F] m-0">
                    Rotate this credential immediately; removing it from code or history is secondary.
                  </p>
                  <div className="flex flex-col gap-2.5">
                    <div className="flex items-start gap-2.5 text-xs font-sans text-[#14141A]">
                      <span className="w-5 h-5 rounded-full bg-[#14141A] text-white flex items-center justify-center font-mono text-[11px] font-bold flex-shrink-0 mt-0.5">1</span>
                      <div>
                        <strong>Revoke in Provider Console:</strong> Invalidate and delete the exposed key {selectedFinding.masked_secret && <code className="font-mono font-bold text-[#E03E3E]">({selectedFinding.masked_secret})</code>} immediately in the provider dashboard.
                      </div>
                    </div>
                    <div className="flex items-start gap-2.5 text-xs font-sans text-[#14141A]">
                      <span className="w-5 h-5 rounded-full bg-[#14141A] text-white flex items-center justify-center font-mono text-[11px] font-bold flex-shrink-0 mt-0.5">2</span>
                      <div>
                        <strong>Rotate Production Secrets:</strong> Provision a replacement credential and inject it via environment variables or a secrets manager.
                      </div>
                    </div>
                    <div className="flex items-start gap-2.5 text-xs font-sans text-[#14141A]">
                      <span className="w-5 h-5 rounded-full bg-[#14141A] text-white flex items-center justify-center font-mono text-[11px] font-bold flex-shrink-0 mt-0.5">3</span>
                      <div>
                        <strong>Audit Provider Logs:</strong> Review access and activity logs in your provider account for unauthorized operations during the exposure window.
                      </div>
                    </div>
                    <div className="flex items-start gap-2.5 text-xs font-sans text-[#14141A]">
                      <span className="w-5 h-5 rounded-full bg-[#14141A] text-white flex items-center justify-center font-mono text-[11px] font-bold flex-shrink-0 mt-0.5">4</span>
                      <div className="flex flex-col gap-1 w-full">
                        <strong>Purge from Git History (Optional):</strong>
                        <span className="text-[11px] text-[#55555F]">Rewriting git history requires a force-push and will disrupt active branches or other contributors:</span>
                        <pre className="bg-[#14141A] text-[#D6F25B] p-2.5 rounded-[8px] border border-[#14141A] font-mono text-[11px] overflow-x-auto m-0 leading-relaxed">
                          <code>{`# WARNING: Rewriting git history requires a force-push ('git push --force')!\ngit filter-repo --invert-paths --path ${selectedFinding.filepath}\ngit push origin --force --all`}</code>
                        </pre>
                      </div>
                    </div>
                  </div>
                </div>
              )}

            {/* Suppression notice if suppressed */}
            {selectedFinding.state !== 'open' && selectedFinding.reason && (
              <div className="p-3 border-2 border-[#14141A] rounded-[10px] bg-[#F5F4EE] text-xs font-sans">
                <span className="font-bold text-[#14141A] uppercase font-mono block mb-1">
                  Suppression Note:
                </span>
                <span className="text-[#55555F]">{selectedFinding.reason}</span>
              </div>
            )}

            {/* Code Snippet */}
            {selectedFinding.code_snippet && (
              <div className="flex flex-col gap-1.5">
                <span className="font-mono text-xs font-bold uppercase text-[#55555F]">
                  Vulnerable Target Code
                </span>
                <pre className="bg-[#14141A] text-[#D6F25B] p-3 rounded-[10px] border-2 border-[#14141A] overflow-x-auto font-mono text-xs leading-relaxed m-0 max-w-full">
                  <code>{selectedFinding.code_snippet}</code>
                </pre>
              </div>
            )}

            {/* Remediation Blueprint */}
            <div className="flex flex-col gap-2">
              <span className="font-mono text-xs font-bold uppercase text-[#55555F]">
                Remediation Blueprint
              </span>
              <p className="font-sans text-xs text-[#55555F] m-0">
                {selectedFinding.fix_description || 'Static code fix recommendation.'}
              </p>

              {(selectedFinding.fix_before || selectedFinding.fix_after) && (
                <div className="flex flex-col gap-2 mt-1">
                  {selectedFinding.fix_before && (
                    <div>
                      <span className="font-sans font-bold text-[11px] text-[#FF6B3D] flex items-center gap-1 mb-1">
                        <XCircle className="w-3.5 h-3.5" /> Vulnerable Before
                      </span>
                      <pre className="bg-[#FFD9CC] border-2 border-[#14141A] text-[#14141A] p-2.5 rounded-[10px] font-mono text-xs overflow-x-auto m-0 max-w-full">
                        <code>{selectedFinding.fix_before}</code>
                      </pre>
                    </div>
                  )}
                  {selectedFinding.fix_after && (
                    <div>
                      <span className="font-sans font-bold text-[11px] text-[#14141A] flex items-center gap-1 mb-1">
                        <CheckCircle className="w-3.5 h-3.5 text-[#14141A]" /> Secured Fix
                      </span>
                      <pre className="bg-[#DDF58A] border-2 border-[#14141A] text-[#14141A] p-2.5 rounded-[10px] font-mono text-xs overflow-x-auto m-0 max-w-full">
                        <code>{selectedFinding.fix_after}</code>
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Official advisory link */}
            {selectedFinding.doc_url && (
              <div>
                <a
                  href={selectedFinding.doc_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 font-sans font-bold text-xs text-[#14141A] hover:underline"
                >
                  <span>Official security advisory docs</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            )}

            {/* Automated Verified Fix (Auto-Fix) Section */}
            {!isSelectedSecret && (
            <div className="flex flex-col gap-3 p-4 border-2 border-[#14141A] rounded-[14px] bg-[#F5F4EE]">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-1.5 font-sans font-bold text-sm text-[#14141A]">
                  <Sparkles className="w-4 h-4 text-[#14141A]" />
                  <span>Automated Verified Fix</span>
                </div>
                {fixAttempt && (
                  <Chip
                    label={
                      fixAttempt.status === 'verified'
                        ? 'VERIFIED'
                        : fixAttempt.status === 'pr_opened'
                        ? 'PR OPENED'
                        : fixAttempt.status === 'merged'
                        ? 'PR MERGED'
                        : fixAttempt.status === 'rejected'
                        ? 'REJECTED'
                        : 'GENERATED'
                    }
                    variant={
                      fixAttempt.status === 'verified'
                        ? 'verified'
                        : fixAttempt.status === 'pr_opened' || fixAttempt.status === 'merged'
                        ? 'pr_opened'
                        : fixAttempt.status === 'rejected'
                        ? 'rejected'
                        : 'generating'
                    }
                  />
                )}
              </div>

              {fixError && (
                <div className="p-3 border-2 border-[#FF6B3D] rounded-[10px] bg-[#FFE5E7] text-xs font-sans text-[#14141A]">
                  <strong className="block font-bold">Auto-Fix Error:</strong>
                  <span>{fixError}</span>
                </div>
              )}

              {generatingFix ? (
                <div className="p-4 border-2 border-[#14141A] rounded-[10px] bg-white flex flex-col items-center justify-center gap-2 text-center">
                  <div className="w-6 h-6 border-2 border-[#14141A] border-t-transparent rounded-full animate-spin" />
                  <span className="font-sans font-bold text-xs text-[#14141A]">
                    Generating & Verifying Security Patch...
                  </span>
                  <span className="font-mono text-[11px] text-[#55555F]">
                    Extracting AST context, executing patch generation, and running sandboxed re-scans.
                  </span>
                </div>
              ) : fixAttempt ? (
                <div className="flex flex-col gap-3">
                  {/* Verified state details */}
                  {fixAttempt.status === 'verified' && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-[11px] font-bold px-2 py-0.5 rounded border border-[#14141A] bg-[#D6F25B] text-[#14141A]">
                        ✓ Syntax Valid
                      </span>
                      <span className="font-mono text-[11px] font-bold px-2 py-0.5 rounded border border-[#14141A] bg-[#D6F25B] text-[#14141A]">
                        ✓ Issue Resolved
                      </span>
                      <span className="font-mono text-[11px] font-bold px-2 py-0.5 rounded border border-[#14141A] bg-[#D6F25B] text-[#14141A]">
                        ✓ Zero Regressions
                      </span>
                    </div>
                  )}

                  {/* PR Opened state */}
                  {(fixAttempt.status === 'pr_opened' || fixAttempt.status === 'merged') && fixAttempt.pr_url && (
                    <div className="p-3 border-2 border-[#14141A] rounded-[10px] bg-white flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <GitPullRequest className="w-4 h-4 text-[#14141A]" />
                        <span className="font-sans font-bold text-xs text-[#14141A]">
                          Pull Request #{fixAttempt.pr_number} created
                        </span>
                      </div>
                      <a
                        href={fixAttempt.pr_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 font-sans font-bold text-xs text-[#14141A] hover:underline"
                      >
                        <span>View on GitHub</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    </div>
                  )}

                  {/* Rejection callout */}
                  {fixAttempt.status === 'rejected' && (
                    <div className="p-3 border-2 border-[#14141A] rounded-[10px] bg-[#FFE5E7] text-xs font-sans text-[#14141A]">
                      <span className="font-bold block mb-1">Patch Failed Sandbox Verification:</span>
                      <span className="text-[#55555F]">{fixAttempt.rejection_reason || 'Re-scan detected remaining or new vulnerabilities.'}</span>
                    </div>
                  )}

                  {/* Diff View */}
                  {fixAttempt.diff && (
                    <CodeDiff
                      diff={fixAttempt.diff}
                      filename={fixAttempt.target_file}
                      maxHeight="max-h-[300px]"
                    />
                  )}

                  {/* Explanation */}
                  {fixAttempt.explanation && (
                    <p className="font-sans text-xs text-[#55555F] m-0 bg-white p-2.5 rounded-[10px] border border-[#E2E0D6]">
                      <strong className="text-[#14141A] block mb-0.5 font-bold">Fix Explanation:</strong>
                      {fixAttempt.explanation}
                    </p>
                  )}

                  {/* Actions for fix */}
                  <div className="flex items-center gap-2 flex-wrap pt-1">
                    {fixAttempt.status === 'verified' && (
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={handleCreateFixPR}
                        disabled={creatingFixPR}
                      >
                        <GitPullRequest className="w-3.5 h-3.5" />
                        <span>{creatingFixPR ? 'Opening PR...' : 'Open Fix PR'}</span>
                      </Button>
                    )}

                    {fixAttempt.status === 'rejected' && (
                      <Button
                        variant="action"
                        size="sm"
                        onClick={handleGenerateFix}
                        disabled={generatingFix}
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>Retry Fix Generation</span>
                      </Button>
                    )}

                    {fixAttempt.diff && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleCopyPatch}
                      >
                        {patchCopied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                        <span>{patchCopied ? 'Copied' : 'Copy patch'}</span>
                      </Button>
                    )}

                    {fixAttempt.patch_code && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleDownloadFixedFile}
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>Download file</span>
                      </Button>
                    )}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <p className="font-sans text-xs text-[#55555F] m-0">
                    Generate an isolated, minimal function-scoped security patch verified by re-scanning with Bandit and Semgrep.
                  </p>
                  <div>
                    <Button
                      variant="action"
                      size="sm"
                      onClick={handleGenerateFix}
                      disabled={generatingFix}
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Generate verified fix</span>
                    </Button>
                  </div>
                </div>
              )}
            </div>
            )}

            {/* Action Bar */}
            <div className="mt-auto pt-4 border-t-2 border-[#E2E0D6] flex justify-between items-center gap-3">
              {selectedFinding.state === 'open' ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setIsSuppressModalOpen(true)}
                >
                  Suppress finding
                </Button>
              ) : (
                <Button
                  variant="action"
                  size="sm"
                  onClick={handleUnsuppress}
                  disabled={isSubmittingAction}
                >
                  {isSubmittingAction ? 'Restoring...' : 'Restore finding to Open'}
                </Button>
              )}

              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedFinding(null)}
              >
                Close
              </Button>
            </div>
          </div>
        </div>
      );})()}

      {/* Suppression Dialog Modal */}
      {isSuppressModalOpen && selectedFinding && (
        <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <div className="w-full max-w-md bg-white border-2 border-[#14141A] rounded-[18px] p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-4">
            <div className="flex justify-between items-start">
              <h3 className="font-sans text-lg font-bold text-[#14141A] m-0">
                Suppress Security Finding
              </h3>
              <button
                onClick={() => setIsSuppressModalOpen(false)}
                className="p-1 rounded-full border-2 border-[#14141A]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="font-sans text-xs text-[#55555F] m-0">
              Suppressed findings will be excluded from pull request blocking and default-branch reporting. An audit log entry will record this action.
            </p>

            <form onSubmit={handleSuppress} className="flex flex-col gap-3">
              <div>
                <label className="font-sans font-bold text-xs text-[#14141A] block mb-1">
                  Suppression Classification
                </label>
                <select
                  value={suppressState}
                  onChange={(e) => setSuppressState(e.target.value as any)}
                  className="w-full px-3 py-2 border-2 border-[#14141A] rounded-[10px] font-sans text-xs bg-white text-[#14141A] focus:outline-none"
                >
                  <option value="suppressed">Suppressed (Accepted Business Risk)</option>
                  <option value="false_positive">False Positive (Scanner Misidentification)</option>
                </select>
              </div>

              <div>
                <label className="font-sans font-bold text-xs text-[#14141A] block mb-1">
                  Justification Reason (Required)
                </label>
                <textarea
                  required
                  rows={3}
                  value={suppressReason}
                  onChange={(e) => setSuppressReason(e.target.value)}
                  placeholder="Explain why this finding is being suppressed..."
                  className="w-full p-2.5 border-2 border-[#14141A] rounded-[10px] font-sans text-xs bg-white text-[#14141A] focus:outline-none placeholder:text-[#888899]"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="ghost"
                  size="sm"
                  type="button"
                  onClick={() => setIsSuppressModalOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  type="submit"
                  disabled={isSubmittingAction || suppressReason.trim().length < 3}
                >
                  {isSubmittingAction ? 'Saving...' : 'Confirm Suppression'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
