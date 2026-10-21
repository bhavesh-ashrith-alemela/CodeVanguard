'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { ArrowRight, GitPullRequest, TrendingUp } from 'lucide-react';
import { 
  Header, StatusCard, Chip, Button, EmptyState, 
  SkeletonStatusCard, SkeletonCard, ErrorState 
} from '@/components/ui';
import { fetchApi, Repository, ScanMetadata, Installation } from '@/lib/api';

interface TrendPoint {
  scan_id: string;
  commit_sha: string;
  timestamp: string;
  score: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  total: number;
}

interface PullSummary {
  pr_number: number;
  title: string;
  branch: string;
  verdict: 'BLOCK' | 'REVIEW' | 'SAFE';
  new_findings_count: number;
  timestamp: string;
}

export default function RepoOverviewPage() {
  const params = useParams();
  const router = useRouter();
  const repoId = params.id as string;

  const [allRepos, setAllRepos] = useState<Repository[]>([]);
  const [repo, setRepo] = useState<Repository | null>(null);
  const [installation, setInstallation] = useState<Installation | null>(null);
  const [scans, setScans] = useState<ScanMetadata[]>([]);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [recentPulls, setRecentPulls] = useState<PullSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Scan execution and live progress polling state
  const [isScanning, setIsScanning] = useState(false);
  const [progressStage, setProgressStage] = useState<string | null>(null);
  const activePollRef = useRef<NodeJS.Timeout | null>(null);

  const loadData = useCallback(async () => {
    if (!repoId) return;
    try {
      setError(null);

      // Load all user repositories for RepoSwitcher
      const reposRes = await fetchApi('/api/repos');
      if (reposRes.status === 401) {
        router.push(`/login?return_to=/repos/${repoId}`);
        return;
      }
      if (reposRes.ok) {
        const data = await reposRes.json();
        setAllRepos(data.repositories || []);
      }

      // Load specific repository details and scan history
      const res = await fetchApi(`/api/repos/${repoId}`);
      if (res.status === 401) {
        router.push(`/login?return_to=/repos/${repoId}`);
        return;
      }
      if (res.status === 403) {
        setError('Access denied: You are not authorized to view this repository.');
        return;
      }
      if (res.status === 404) {
        setError('Repository not found or has been disconnected.');
        return;
      }
      if (!res.ok) {
        throw new Error('Failed to load repository details');
      }

      const data = await res.json();
      setRepo(data.repository);
      setInstallation(data.installation);
      setScans(data.scans || []);

      // Load trend
      const trendRes = await fetchApi(`/api/repos/${repoId}/trend`);
      if (trendRes.ok) {
        const trendData = await trendRes.json();
        setTrend(trendData.trend || []);
      }

      // Load PRs
      const pullsRes = await fetchApi(`/api/repos/${repoId}/pulls`);
      if (pullsRes.ok) {
        const pullsData = await pullsRes.json();
        setRecentPulls((pullsData.pull_requests || []).slice(0, 3));
      }
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred');
    } finally {
      setLoading(false);
    }
  }, [repoId, router]);

  useEffect(() => {
    loadData();
    return () => {
      if (activePollRef.current) {
        clearInterval(activePollRef.current);
      }
    };
  }, [loadData]);

  // Live polling helper for running scan
  const startPollingScan = (scanId: string) => {
    setIsScanning(true);
    setProgressStage('queued');

    const pollInterval = setInterval(async () => {
      try {
        const res = await fetchApi(`/api/scans/${scanId}/status`);
        if (!res.ok) return;
        const data = await res.json();

        if (data.progress) {
          setProgressStage(data.progress);
        }

        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(pollInterval);
          activePollRef.current = null;
          setIsScanning(false);
          setProgressStage(null);
          loadData();
        }
      } catch {
        // Polling retry
      }
    }, 1200);

    activePollRef.current = pollInterval;
  };

  const handleScanNow = async () => {
    if (!repo || isScanning) return;
    setIsScanning(true);
    setProgressStage('queued');

    try {
      const res = await fetchApi(`/api/repos/${repo.id}/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ branch: repo.default_branch || 'main' })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to initialize scan');
      }

      startPollingScan(data.scan_id);
    } catch (err: any) {
      setIsScanning(false);
      setProgressStage(null);
      alert(err.message || 'Error initializing scan.');
    }
  };

  const formatProgressLabel = () => {
    if (!isScanning) return 'Scan now';
    if (!progressStage || progressStage === 'queued') return 'Queued...';
    if (progressStage === 'downloading') return 'Downloading...';
    if (progressStage === 'extracting') return 'Extracting...';
    if (progressStage === 'filtering') return 'Filtering...';
    if (progressStage === 'scanning bandit') return 'Scanning Bandit...';
    if (progressStage === 'scanning semgrep') return 'Scanning Semgrep...';
    if (progressStage === 'saving') return 'Saving...';
    return `${progressStage}...`;
  };

  const formatTimeAgo = (timestamp?: string) => {
    if (!timestamp) return 'recently';
    try {
      const date = new Date(timestamp);
      const diffMs = Date.now() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 1) return 'just now';
      if (diffMins < 60) return `${diffMins} min ago`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      return date.toLocaleDateString();
    } catch {
      return timestamp;
    }
  };

  const defaultBranch = repo?.default_branch || 'main';
  const latestDefaultScan = scans.find(
    (s) => (s.branch === defaultBranch || !s.branch) && s.trigger !== 'pr'
  );

  // SVG Trend Line calculation
  const renderTrendSvg = () => {
    if (trend.length < 2) return null;
    const width = 340;
    const height = 50;
    const padding = 8;

    const scores = trend.map(t => t.score);
    const minScore = Math.max(0, Math.min(...scores) - 10);
    const maxScore = 100;
    const range = maxScore - minScore || 1;

    const points = trend.map((t, i) => {
      const x = padding + (i / (trend.length - 1)) * (width - 2 * padding);
      const y = height - padding - ((t.score - minScore) / range) * (height - 2 * padding);
      return { x, y, score: t.score };
    });

    const polylinePoints = points.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    const latestScore = trend[trend.length - 1].score;

    return (
      <div className="flex flex-col gap-1.5 pt-1">
        <div className="flex justify-between items-center text-xs">
          <span className="font-mono text-[#55555F]">Default Branch Baseline</span>
          <span className="font-mono font-bold text-[#14141A]">Score: {latestScore}/100</span>
        </div>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-12 overflow-visible"
          role="img"
          aria-label="Security score trend line"
        >
          <polyline
            fill="none"
            stroke="#14141A"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            points={polylinePoints}
          />
          {points.map((p, idx) => (
            <circle
              key={idx}
              cx={p.x}
              cy={p.y}
              r={idx === points.length - 1 ? 4.5 : 3}
              fill={p.score >= 90 ? "#D6F25B" : p.score >= 75 ? "#FFC93C" : "#FF6B3D"}
              stroke="#14141A"
              strokeWidth="2"
            />
          ))}
        </svg>
      </div>
    );
  };

  return (
    <div className="max-w-[1160px] mx-auto w-full py-4 px-4 sm:px-6 flex flex-col gap-6">
      {/* Header with activeTab="overview" */}
      <Header
        currentRepo={repo || undefined}
        repositories={allRepos}
        activeTab="overview"
        rightAction={
          repo ? (
            <Button
              variant="action"
              size="md"
              onClick={handleScanNow}
              disabled={isScanning}
              loading={isScanning}
            >
              {formatProgressLabel()}
            </Button>
          ) : undefined
        }
      />

      {/* Screen States */}
      {loading ? (
        <div className="flex flex-col gap-6">
          <SkeletonStatusCard />
          <SkeletonCard />
        </div>
      ) : error ? (
        <ErrorState
          title="Repository Error"
          message={error}
          onRetry={loadData}
        />
      ) : repo ? (
        <>
          {/* StatusCard for latest default-branch scan */}
          <StatusCard
            status={
              isScanning
                ? 'running'
                : latestDefaultScan
                ? latestDefaultScan.status
                : 'not_scanned'
            }
            branch={latestDefaultScan?.branch || defaultBranch}
            timestamp={latestDefaultScan?.timestamp}
            critical={latestDefaultScan?.critical_count || 0}
            high={latestDefaultScan?.high_count || 0}
            medium={latestDefaultScan?.medium_count || 0}
            low={latestDefaultScan?.low_count || 0}
            totalIssues={latestDefaultScan?.total_issues || 0}
          />

          <div className="flex gap-6 flex-wrap items-start">
            {/* Left: Scan History & Inline SVG Trend Line */}
            <section className="border-2 border-[#14141A] rounded-[18px] bg-white p-5 md:p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-4 flex-[1.6_1_460px]">
              <div className="flex items-center justify-between pb-1">
                <h3 className="text-xl font-bold font-sans text-[#14141A] m-0">
                  Scan History
                </h3>
                <span className="font-mono text-xs text-[#55555F]">
                  {scans.length} {scans.length === 1 ? 'run' : 'runs'}
                </span>
              </div>

              {/* Lightweight inline SVG Trend line */}
              {renderTrendSvg()}

              {scans.length === 0 ? (
                <EmptyState
                  title="No scans yet"
                  description="Initialize your first static application security scan on the default branch."
                  actionLabel="Scan now"
                  onAction={handleScanNow}
                  className="shadow-none border-dashed"
                />
              ) : (
                <div className="flex flex-col divide-y-2 divide-[#E2E0D6] pt-1">
                  {scans.map((s) => {
                    const shortSha = s.commit_sha ? s.commit_sha.slice(0, 7) : 'head';
                    const branchName = s.branch || defaultBranch;
                    const timeText = formatTimeAgo(s.timestamp);

                    const chipVariant =
                      s.status === 'completed'
                        ? 'safe'
                        : s.status === 'failed'
                        ? 'failed'
                        : 'running';

                    return (
                      <div
                        key={s.id}
                        className="py-3 flex items-center justify-between gap-3 flex-wrap"
                      >
                        <div className="flex items-center gap-3 flex-wrap min-w-[200px]">
                          <span className="font-mono text-xs text-[#14141A] font-bold">
                            {shortSha}
                          </span>
                          <span className="font-mono text-xs text-[#55555F]">
                            {branchName}
                          </span>
                          <span className="font-mono text-xs text-[#55555F]">
                            {timeText}
                          </span>
                          <Chip
                            label={s.status.toUpperCase()}
                            variant={chipVariant}
                          />
                        </div>

                        <Link
                          href={`/results?scan_id=${s.id}`}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 border-2 border-[#14141A] rounded-full font-sans text-xs font-bold hover:bg-[#F5F4EE] transition-colors"
                        >
                          <span>View</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {/* Right: Pull Requests Preview Card (matching Dashboard.dc.html) */}
            <section className="border-2 border-[#14141A] rounded-[18px] bg-white p-5 md:p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-3 flex-[1_1_300px]">
              <div className="flex items-center justify-between">
                <h3 className="text-xl font-bold font-sans text-[#14141A] m-0">
                  Pull requests
                </h3>
                <GitPullRequest className="w-5 h-5 text-[#14141A]" />
              </div>

              {recentPulls.length === 0 ? (
                <p className="font-sans text-xs text-[#55555F] m-0 py-4">
                  No active pull requests scanned yet.
                </p>
              ) : (
                <div className="flex flex-col divide-y-2 divide-[#E2E0D6]">
                  {recentPulls.map((pr) => {
                    const verdictVariant =
                      pr.verdict === 'BLOCK'
                        ? 'block'
                        : pr.verdict === 'REVIEW'
                        ? 'attention'
                        : 'safe';

                    return (
                      <Link
                        key={pr.pr_number}
                        href={`/repos/${repoId}/pulls/${pr.pr_number}`}
                        className="py-3 flex items-center justify-between gap-3 hover:bg-[#F5F4EE] px-1 rounded transition-colors"
                      >
                        <div className="flex-1 min-w-[130px]">
                          <div className="font-sans font-medium text-sm text-[#14141A] truncate">
                            {pr.title}
                          </div>
                          <div className="font-mono text-xs text-[#55555F]">
                            #{pr.pr_number} · {pr.new_findings_count} new
                          </div>
                        </div>

                        <Chip label={pr.verdict} variant={verdictVariant} />
                      </Link>
                    );
                  })}
                </div>
              )}

              <Link
                href={`/repos/${repoId}/pulls`}
                className="inline-block mt-2 font-sans font-bold text-xs text-[#14141A] hover:underline"
              >
                View all pull requests →
              </Link>
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}
