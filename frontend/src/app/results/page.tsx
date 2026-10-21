'use client';

import React, { useState, useEffect, useMemo, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { 
  Shield, AlertTriangle, FileText, CheckCircle, XCircle, Search, 
  ExternalLink, ArrowLeft, ChevronDown, Loader2, Sparkles 
} from 'lucide-react';
import { 
  StatusCard, Button, Chip, SkeletonStatusCard, SkeletonCard, 
  ErrorState, EmptyState 
} from '@/components/ui';
import { fetchApi, API_BASE, ScanMetadata, Issue } from '@/lib/api';

const STAGES: Record<string, { label: string; desc: string; percent: number }> = {
  queued: { label: 'QUEUED IN WORKER', desc: 'Job dispatched to background worker queue...', percent: 15 },
  downloading: { label: 'DOWNLOADING ARCHIVE', desc: 'Streaming tarball archive securely from GitHub...', percent: 30 },
  extracting: { label: 'SAFE ARCHIVE EXTRACTION', desc: 'Validating archive members, rejecting symlinks and traversal paths...', percent: 45 },
  filtering: { label: 'FILTERING WORKSPACE', desc: 'Applying .codevanguardignore, stripping minified assets and lockfiles...', percent: 60 },
  'scanning bandit': { label: 'ANALYZING BANDIT AST', desc: 'Executing Python AST security and injection checks...', percent: 75 },
  'scanning semgrep': { label: 'RUNNING SEMGREP ENGINE', desc: 'Running offline pattern rules across codebase...', percent: 85 },
  saving: { label: 'COMPUTING FINGERPRINTS', desc: 'Generating deterministic issue fingerprints and saving reports...', percent: 95 },
  completed: { label: 'COMPLETED', desc: 'Analysis completed successfully!', percent: 100 },
  failed: { label: 'FAILED', desc: 'Scan execution encountered an error.', percent: 100 }
};

const ITEMS_PER_PAGE = 10;

function ResultsClient() {
  const searchParams = useSearchParams();
  const router = useRouter();
  
  const scanId = searchParams.get('id') || searchParams.get('scan_id');

  const [scan, setScan] = useState<ScanMetadata | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  
  // Filter States
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [scannerFilter, setScannerFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [currentPage, setCurrentPage] = useState<number>(1);
  
  // Polling Timer States
  const [elapsedTime, setElapsedTime] = useState<number>(0);
  const [scanStartTime] = useState<number>(Date.now());

  useEffect(() => {
    if (!scanId) {
      setLoading(false);
      setErrorMsg("No scan ID was provided.");
      return;
    }

    let timeoutId: NodeJS.Timeout;
    let isCancelled = false;
    let pollDelay = 1000;
    
    const timerId = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - scanStartTime) / 1000));
    }, 1000);

    const pollStatus = async () => {
      try {
        const response = await fetchApi(`/api/scans/${scanId}/status`);
        if (!response.ok) {
          if (response.status === 404) {
            setErrorMsg("Scan record not found in system registry.");
            setLoading(false);
            return;
          }
          throw new Error("Unable to retrieve scan status.");
        }
        const data = await response.json();
        setScan(data);
        
        if (data.status === 'completed') {
          clearInterval(timerId);
          fetchFindings();
          return;
        } else if (data.status === 'failed') {
          clearInterval(timerId);
          setErrorMsg(data.error_message || "Static analysis engine failed.");
          setLoading(false);
          return;
        } else {
          pollDelay = Math.min(pollDelay + 500, 3500);
        }
      } catch (error: any) {
        pollDelay = Math.min(pollDelay * 1.5, 5000);
      }

      if (!isCancelled) {
        timeoutId = setTimeout(pollStatus, pollDelay);
      }
    };

    const fetchFindings = async () => {
      try {
        const response = await fetchApi(`/api/scans/${scanId}/issues`);
        if (!response.ok) throw new Error("Failed to load issues registry.");
        const data = await response.json();
        
        setScan(data.scan);
        setIssues(data.issues || []);
        setLoading(false);
      } catch (error: any) {
        setErrorMsg(error.message || "Failed to fetch scan results.");
        setLoading(false);
      }
    };

    pollStatus();

    return () => {
      isCancelled = true;
      clearTimeout(timeoutId);
      clearInterval(timerId);
    };
  }, [scanId, scanStartTime]);

  // Reset page when filter changes
  useEffect(() => {
    setCurrentPage(1);
  }, [severityFilter, scannerFilter, searchQuery]);

  // Filtered issues
  const filteredIssues = useMemo(() => {
    return issues.filter(issue => {
      const matchSeverity = severityFilter === 'all' || issue.severity === severityFilter;
      const matchScanner = scannerFilter === 'all' || issue.scanner === scannerFilter;
      const searchString = `${issue.filepath} ${issue.message} ${issue.rule_id} ${issue.fix_title}`.toLowerCase();
      const matchSearch = !searchQuery || searchString.includes(searchQuery.toLowerCase());
      return matchSeverity && matchScanner && matchSearch;
    });
  }, [issues, severityFilter, scannerFilter, searchQuery]);

  // Pagination calculation
  const totalPages = Math.max(1, Math.ceil(filteredIssues.length / ITEMS_PER_PAGE));
  const paginatedIssues = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    return filteredIssues.slice(start, start + ITEMS_PER_PAGE);
  }, [filteredIssues, currentPage]);

  // Top 3 issues for "Fix first"
  const topIssues = useMemo(() => {
    const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
    return [...issues].sort((a, b) => {
      const rankA = severityOrder[a.severity] ?? 4;
      const rankB = severityOrder[b.severity] ?? 4;
      return rankA - rankB;
    }).slice(0, 3);
  }, [issues]);

  const currentStage = STAGES[scan?.progress || 'queued'] || {
    label: (scan?.progress || 'SCANNING').toUpperCase(),
    desc: 'Executing security checks...',
    percent: 50
  };

  const backUrl = scan?.repo_id ? `/repos/${scan.repo_id}` : '/dashboard';
  const backLabel = scan?.repo_id ? 'Back to repository' : 'Back to Dashboard';

  // State 1: Invalid Scan ID
  if (!scanId) {
    return (
      <div className="max-w-[1160px] mx-auto w-full py-12 px-4">
        <ErrorState
          title="Invalid Scan Request"
          message="No scan identification parameter was provided. Please return to the dashboard and trigger a scan."
          onRetry={() => router.push('/dashboard')}
        />
      </div>
    );
  }

  // State 2: Active Scan Polling / Loading
  if (loading && (!scan || (scan.status !== 'completed' && scan.status !== 'failed'))) {
    return (
      <div className="max-w-[1160px] mx-auto w-full py-8 px-4 sm:px-6 flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <Link
            href={backUrl}
            className="inline-flex items-center gap-1.5 font-sans font-bold text-sm text-[#14141A] hover:underline"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>{backLabel}</span>
          </Link>
        </div>

        {/* Live scanning progress card */}
        <div className="border-2 border-[#14141A] rounded-[18px] bg-white p-6 md:p-8 shadow-[5px_5px_0_#14141A] flex flex-col items-center text-center gap-6">
          <div className="relative flex items-center justify-center w-16 h-16">
            <span className="absolute w-14 h-14 rounded-full border-4 border-[#D6F25B] animate-ping opacity-60"></span>
            <Loader2 className="w-8 h-8 text-[#14141A] animate-spin relative z-10" />
          </div>

          <div className="flex flex-col gap-2 max-w-md">
            <Chip label={currentStage.label} variant="running" className="self-center" />
            <h2 className="text-2xl font-bold font-sans text-[#14141A] m-0">
              Active Security Scan
            </h2>
            <p className="font-sans text-sm text-[#55555F] m-0">
              {currentStage.desc}
            </p>
          </div>

          <div className="w-full max-w-md flex flex-col gap-2">
            <div className="h-4 bg-[#F5F4EE] border-2 border-[#14141A] rounded-full overflow-hidden">
              <div 
                className="h-full bg-[#D6F25B] border-r-2 border-[#14141A] transition-all duration-500" 
                style={{ width: `${currentStage.percent}%` }}
              />
            </div>
            <div className="flex items-center justify-between font-mono text-xs text-[#55555F]">
              <span>STAGE: <strong className="text-[#14141A] uppercase">{scan?.progress || 'QUEUED'}</strong></span>
              <span>TIME ELAPSED: <strong className="text-[#14141A]">{elapsedTime}s</strong></span>
            </div>
          </div>
        </div>

        <SkeletonStatusCard />
      </div>
    );
  }

  // State 3: Scan Failed / Error
  if (errorMsg || (scan && scan.status === 'failed')) {
    return (
      <div className="max-w-[1160px] mx-auto w-full py-8 px-4 sm:px-6 flex flex-col gap-6">
        <Link
          href={backUrl}
          className="inline-flex items-center gap-1.5 font-sans font-bold text-sm text-[#14141A] hover:underline"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{backLabel}</span>
        </Link>

        <ErrorState
          title="Scan Execution Failed"
          message={errorMsg || scan?.error_message || "The static analysis engines encountered an unexpected error while scanning."}
          onRetry={() => window.location.reload()}
        />
      </div>
    );
  }

  if (!scan) return null;

  return (
    <div className="max-w-[1160px] mx-auto w-full py-6 px-4 sm:px-6 flex flex-col gap-6">
      
      {/* Top Navigation & Compliance Export Bar */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Link
          href={backUrl}
          className="inline-flex items-center gap-1.5 font-sans font-bold text-sm text-[#14141A] hover:underline"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{backLabel}</span>
        </Link>

        {/* Export formats */}
        <div className="flex items-center gap-2 flex-wrap font-sans text-xs font-bold">
          <span className="text-[#55555F] uppercase font-mono text-xs">Export report:</span>
          <a
            href={`${API_BASE}/api/scans/${scanId}/export/pdf`}
            download
            className="inline-flex items-center gap-1 px-3 py-1.5 border-2 border-[#14141A] rounded-full bg-white text-[#14141A] shadow-[2px_2px_0_#14141A] hover:bg-[#F5F4EE] transition-all"
          >
            <FileText className="w-3.5 h-3.5" /> PDF
          </a>
          <a
            href={`${API_BASE}/api/scans/${scanId}/export/html`}
            download
            className="inline-flex items-center gap-1 px-3 py-1.5 border-2 border-[#14141A] rounded-full bg-white text-[#14141A] shadow-[2px_2px_0_#14141A] hover:bg-[#F5F4EE] transition-all"
          >
            <FileText className="w-3.5 h-3.5" /> HTML
          </a>
          <a
            href={`${API_BASE}/api/scans/${scanId}/export/json`}
            download
            className="inline-flex items-center gap-1 px-3 py-1.5 border-2 border-[#14141A] rounded-full bg-white text-[#14141A] shadow-[2px_2px_0_#14141A] hover:bg-[#F5F4EE] transition-all"
          >
            <FileText className="w-3.5 h-3.5" /> JSON
          </a>
          <a
            href={`${API_BASE}/api/scans/${scanId}/export/csv`}
            download
            className="inline-flex items-center gap-1 px-3 py-1.5 border-2 border-[#14141A] rounded-full bg-white text-[#14141A] shadow-[2px_2px_0_#14141A] hover:bg-[#F5F4EE] transition-all"
          >
            <FileText className="w-3.5 h-3.5" /> CSV
          </a>
          <a
            href={`${API_BASE}/api/scans/${scanId}/export/sarif`}
            download
            className="inline-flex items-center gap-1 px-3 py-1.5 border-2 border-[#14141A] rounded-full bg-white text-[#14141A] shadow-[2px_2px_0_#14141A] hover:bg-[#F5F4EE] transition-all"
          >
            <FileText className="w-3.5 h-3.5" /> SARIF
          </a>
        </div>
      </div>

      {/* Target Metadata Bar */}
      <div className="border-2 border-[#14141A] rounded-[14px] bg-[#14141A] text-white p-4 flex flex-wrap items-center justify-between gap-3 font-mono text-xs">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 font-bold">
            <span className="text-[#D6F25B] uppercase">TARGET:</span>
            <span>{scan.filename}</span>
          </div>
          {scan.commit_sha && (
            <div className="bg-[#24242E] px-2 py-0.5 rounded border border-[#3A3A4A] text-[11px]">
              <span className="text-[#888899]">SHA: </span>
              <span className="text-[#D6F25B] font-bold">{scan.commit_sha.slice(0, 7)}</span>
            </div>
          )}
          {scan.branch && (
            <div className="bg-[#24242E] px-2 py-0.5 rounded border border-[#3A3A4A] text-[11px]">
              <span className="text-[#888899]">BRANCH: </span>
              <span className="text-white font-bold">{scan.branch}</span>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-4 text-[11px] text-[#A0A0B0]">
          <span>FILES SCANNED: <strong className="text-[#D6F25B]">{scan.files_scanned ?? 1}</strong></span>
          <span>SKIPPED: <strong className="text-white">{scan.files_skipped ?? 0}</strong></span>
          {scan.duration_ms ? (
            <span>DURATION: <strong className="text-white">{scan.duration_ms}ms</strong></span>
          ) : null}
        </div>
      </div>

      {/* Step 1 Summary Card: StatusCard */}
      <StatusCard
        status={scan.status}
        branch={scan.branch || 'main'}
        timestamp={scan.timestamp}
        critical={scan.critical_count}
        high={scan.high_count}
        medium={scan.medium_count}
        low={scan.low_count}
        totalIssues={scan.total_issues}
      />

      {/* State 4: Clean run (Zero issues detected) */}
      {issues.length === 0 ? (
        <EmptyState
          icon={<Shield className="w-8 h-8 text-[#14141A]" />}
          title="Clean Code — Zero Vulnerabilities Detected"
          description="The static analysis engines completed successfully with zero security defects found across all scanned files and AST nodes."
          actionLabel={backLabel}
          actionHref={backUrl}
        />
      ) : (
        <>
          {/* Fix first Section: Top 3 priority issues */}
          <section className="border-2 border-[#14141A] rounded-[18px] bg-white p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-4">
            <div className="flex justify-between items-baseline gap-3 flex-wrap">
              <h2 className="text-xl md:text-2xl font-bold font-sans text-[#14141A] m-0">
                Fix first
              </h2>
              <span className="font-mono text-xs text-[#55555F]">
                top {topIssues.length} of {issues.length}
              </span>
            </div>

            {/* Top 1 Featured Remediation Box */}
            {topIssues.length > 0 && (
              <div className="p-4 border-2 border-[#14141A] rounded-[14px] bg-[#F6FBDD] flex flex-col gap-3">
                <div className="flex items-center gap-3 flex-wrap">
                  <Chip
                    label={topIssues[0].severity.toUpperCase()}
                    variant={topIssues[0].severity}
                  />
                  <div>
                    <div className="font-sans font-bold text-sm text-[#14141A]">
                      {topIssues[0].fix_title}
                    </div>
                    <div className="font-mono text-xs text-[#55555F]">
                      {topIssues[0].filepath}:{topIssues[0].line_number}
                    </div>
                  </div>
                </div>

                {/* Diff box */}
                {(topIssues[0].fix_before || topIssues[0].fix_after) && (
                  <pre className="font-mono text-xs md:text-[13px] leading-relaxed overflow-x-auto border-2 border-[#14141A] rounded-[10px] bg-white p-3 m-0 max-w-full">
                    {topIssues[0].fix_before && (
                      <span className="block bg-[#FFD9CC] text-[#14141A] px-1 rounded-sm">
                        − {topIssues[0].fix_before}
                      </span>
                    )}
                    {topIssues[0].fix_after && (
                      <span className="block bg-[#DDF58A] text-[#14141A] px-1 rounded-sm mt-1">
                        + {topIssues[0].fix_after}
                      </span>
                    )}
                  </pre>
                )}

                <div className="flex justify-between items-center gap-3 flex-wrap">
                  <span className="font-mono text-xs text-[#55555F]">
                    {topIssues[0].fix_description || 'Static remediation · Review before applying'}
                  </span>
                  <div className="flex items-center gap-3">
                    {scan?.repo_id && (
                      <Link
                        href={`/repos/${scan.repo_id}/findings?search=${encodeURIComponent(topIssues[0].rule_id)}`}
                        className="font-sans text-xs font-bold text-[#14141A] hover:underline inline-flex items-center gap-1 bg-[#D6F25B] px-2.5 py-1 rounded-md border border-[#14141A]"
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>Auto-fix finding</span>
                      </Link>
                    )}
                    {topIssues[0].doc_url && (
                      <a
                        href={topIssues[0].doc_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-sans text-xs font-bold text-[#14141A] hover:underline inline-flex items-center gap-1"
                      >
                        <span>Advisory docs</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Top 2 and 3 Finding Rows */}
            {topIssues.slice(1).map((issue) => (
              <div
                key={issue.id}
                className="pt-3 pb-2 border-t-2 border-[#E2E0D6] flex items-center justify-between gap-3 flex-wrap"
              >
                <div className="flex items-center gap-3 flex-wrap min-w-[200px]">
                  <Chip
                    label={issue.severity.toUpperCase()}
                    variant={issue.severity}
                  />
                  <div>
                    <div className="font-sans font-bold text-sm text-[#14141A]">
                      {issue.fix_title}
                    </div>
                    <div className="font-mono text-xs text-[#55555F]">
                      {issue.filepath}:{issue.line_number}
                    </div>
                  </div>
                </div>

                <span className="font-sans text-xs text-[#55555F] max-w-md">
                  {issue.fix_description}
                </span>
              </div>
            ))}

            <a
              href="#findings-table"
              className="inline-block mt-1 font-sans font-bold text-sm text-[#14141A] hover:underline"
            >
              View all {issues.length} findings ↓
            </a>
          </section>

          {/* Full Findings Table Section */}
          <section
            id="findings-table"
            className="border-2 border-[#14141A] rounded-[18px] bg-white p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-5"
          >
            <div className="flex justify-between items-center gap-3 flex-wrap">
              <h2 className="text-xl md:text-2xl font-bold font-sans text-[#14141A] m-0">
                All Findings
              </h2>
              <span className="font-mono text-xs text-[#55555F]">
                Showing {filteredIssues.length} of {issues.length} findings
              </span>
            </div>

            {/* Filters and Search Toolbar */}
            <div className="flex flex-col lg:flex-row gap-3 items-stretch lg:items-center justify-between">
              
              {/* Severity filter tabs */}
              <div className="flex flex-wrap gap-1 bg-[#F5F4EE] p-1 rounded-full border-2 border-[#14141A] w-fit font-sans text-xs font-bold">
                {(['all', 'critical', 'high', 'medium', 'low'] as const).map((sev) => {
                  const isActive = severityFilter === sev;
                  let count = issues.length;
                  if (sev === 'critical') count = scan.critical_count;
                  if (sev === 'high') count = scan.high_count;
                  if (sev === 'medium') count = scan.medium_count;
                  if (sev === 'low') count = scan.low_count;

                  return (
                    <button
                      key={sev}
                      onClick={() => setSeverityFilter(sev)}
                      className={`px-3 py-1 rounded-full uppercase transition-all cursor-pointer ${
                        isActive
                          ? 'bg-[#14141A] text-[#F5F4EE]'
                          : 'text-[#14141A] hover:bg-[#E2E0D6]'
                      }`}
                    >
                      {sev} ({count})
                    </button>
                  );
                })}
              </div>

              {/* Scanner filter & text search */}
              <div className="flex flex-col sm:flex-row gap-2.5 flex-grow lg:max-w-lg">
                <select
                  value={scannerFilter}
                  onChange={(e) => setScannerFilter(e.target.value)}
                  className="px-3 py-2 border-2 border-[#14141A] rounded-full font-sans text-xs font-bold bg-white text-[#14141A] focus:outline-none"
                >
                  <option value="all">All Scanners</option>
                  <option value="bandit">Bandit AST Rules</option>
                  <option value="semgrep">Semgrep Rules</option>
                </select>

                <div className="relative flex-grow">
                  <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-[#55555F] pointer-events-none">
                    <Search className="w-4 h-4" />
                  </span>
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search by rule, message or path..."
                    className="w-full pl-9 pr-3 py-2 border-2 border-[#14141A] rounded-full font-sans text-xs bg-white text-[#14141A] focus:outline-none placeholder:text-[#888899]"
                  />
                </div>
              </div>
            </div>

            {/* Findings List */}
            {filteredIssues.length === 0 ? (
              <div className="p-8 text-center bg-[#F5F4EE] border-2 border-[#14141A] rounded-[14px]">
                <p className="font-sans font-bold text-sm text-[#55555F] m-0">
                  No findings match the selected severity, scanner, or search query.
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {paginatedIssues.map((issue) => (
                  <div
                    key={issue.id}
                    className="border-2 border-[#14141A] rounded-[14px] bg-white shadow-[3px_3px_0_#14141A] overflow-hidden"
                  >
                    <details className="group">
                      <summary className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-4 select-none cursor-pointer list-none relative">
                        <div className="flex flex-wrap items-center gap-3">
                          <Chip
                            label={issue.severity.toUpperCase()}
                            variant={issue.severity}
                          />
                          <div className="text-left">
                            <span className="font-sans font-bold text-sm text-[#14141A] mr-2">
                              {issue.fix_title}
                            </span>
                            <span className="font-mono text-xs text-[#55555F] break-all">
                              {issue.filepath}:{issue.line_number}
                            </span>
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-2 text-xs font-mono text-[#55555F] pr-6 md:pr-8">
                          <span className="px-2 py-0.5 rounded border border-[#14141A] text-[10px] font-bold uppercase bg-[#F5F4EE] text-[#14141A]">
                            {issue.scanner}
                          </span>
                          <span>{issue.rule_id}</span>
                          {issue.fingerprint && (
                            <span className="hidden sm:inline-block bg-[#F5F4EE] text-[#55555F] px-1.5 py-0.5 rounded text-[10px] border border-[#E2E0D6]" title={`Deterministic Fingerprint: ${issue.fingerprint}`}>
                              FP: {issue.fingerprint.slice(0, 8)}
                            </span>
                          )}
                        </div>

                        {/* Chevron */}
                        <span className="absolute right-4 top-1/2 -translate-y-1/2 transition-transform duration-200 group-open:rotate-180">
                          <ChevronDown className="w-4 h-4 text-[#14141A]" />
                        </span>
                      </summary>

                      {/* Expandable Details */}
                      <div className="bg-[#F5F4EE] border-t-2 border-[#14141A] p-4 flex flex-col gap-4 text-xs">
                        <div className="flex flex-col gap-1">
                          <span className="font-mono text-[10px] uppercase font-bold text-[#55555F]">
                            Threat Details
                          </span>
                          <p className="font-sans text-xs bg-white p-3 rounded-[10px] border-2 border-[#14141A] text-[#14141A] font-bold m-0">
                            {issue.message}
                          </p>
                        </div>

                        {issue.code_snippet && (
                          <div className="flex flex-col gap-1">
                            <span className="font-mono text-[10px] uppercase font-bold text-[#55555F]">
                              Target Code View ({issue.filepath}:{issue.line_number})
                            </span>
                            <pre className="bg-[#14141A] text-[#D6F25B] p-3 rounded-[10px] border-2 border-[#14141A] overflow-x-auto font-mono text-xs leading-relaxed m-0 max-w-full">
                              <code>{issue.code_snippet}</code>
                            </pre>
                          </div>
                        )}

                        <div className="flex flex-col gap-2">
                          <span className="font-mono text-[10px] uppercase font-bold text-[#55555F]">
                            Blueprint Remediation
                          </span>
                          <p className="font-sans text-xs text-[#55555F] m-0">
                            {issue.fix_description}
                          </p>

                          {(issue.fix_before || issue.fix_after) && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-1">
                              {issue.fix_before && (
                                <div className="flex flex-col gap-1">
                                  <div className="font-sans font-bold text-[11px] text-[#FF6B3D] flex items-center gap-1">
                                    <XCircle className="w-3.5 h-3.5" /> Vulnerable Code
                                  </div>
                                  <pre className="bg-[#FFD9CC] border-2 border-[#14141A] text-[#14141A] p-2.5 rounded-[10px] font-mono text-xs overflow-x-auto m-0 leading-relaxed font-bold max-w-full">
                                    <code>{issue.fix_before}</code>
                                  </pre>
                                </div>
                              )}
                              {issue.fix_after && (
                                <div className="flex flex-col gap-1">
                                  <div className="font-sans font-bold text-[11px] text-[#14141A] flex items-center gap-1">
                                    <CheckCircle className="w-3.5 h-3.5 text-[#14141A]" /> Secured Fix
                                  </div>
                                  <pre className="bg-[#DDF58A] border-2 border-[#14141A] text-[#14141A] p-2.5 rounded-[10px] font-mono text-xs overflow-x-auto m-0 leading-relaxed font-bold max-w-full">
                                    <code>{issue.fix_after}</code>
                                  </pre>
                                </div>
                              )}
                            </div>
                          )}
                        </div>

                        {issue.doc_url && (
                          <div className="flex justify-end pt-1">
                            <a
                              href={issue.doc_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 font-sans font-bold text-xs text-[#14141A] hover:underline"
                            >
                              <span>Official security advisory docs</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          </div>
                        )}
                      </div>
                    </details>
                  </div>
                ))}
              </div>
            )}

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="flex justify-between items-center gap-3 pt-3 border-t-2 border-[#E2E0D6] flex-wrap">
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
        </>
      )}

    </div>
  );
}

export default function ResultsPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-[1160px] mx-auto w-full py-12 px-4 flex flex-col gap-6">
          <SkeletonStatusCard />
          <SkeletonCard />
        </div>
      }
    >
      <ResultsClient />
    </Suspense>
  );
}
