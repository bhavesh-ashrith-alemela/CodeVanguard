'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { 
  ArrowLeft, CheckCircle, XCircle, ExternalLink, ChevronDown, 
  Sparkles, ShieldCheck, AlertOctagon, CheckSquare, Square
} from 'lucide-react';
import { 
  Header, StatusCard, Chip, SkeletonStatusCard, SkeletonCard, ErrorState, EmptyState 
} from '@/components/ui';
import { fetchApi, Repository, ScanMetadata, Issue, PRSummaryRecord } from '@/lib/api';

interface TimelineItem {
  id: string;
  branch: string;
  commit_sha: string;
  status: string;
  verdict: 'BLOCK' | 'REVIEW' | 'SAFE' | 'block' | 'attention' | 'safe';
  progress?: string;
  new_findings_count: number;
  fixed_findings_count: number;
  existing_findings_count: number;
  duration_ms?: number;
  timestamp: string;
}

export default function PullRequestDetailPage() {
  const params = useParams();
  const router = useRouter();
  const repoId = params.id as string;
  const prNumber = params.number as string;

  const [allRepos, setAllRepos] = useState<Repository[]>([]);
  const [repo, setRepo] = useState<Repository | null>(null);
  const [latestScan, setLatestScan] = useState<ScanMetadata | null>(null);
  const [newIssues, setNewIssues] = useState<Issue[]>([]);
  const [existingIssuesCount, setExistingIssuesCount] = useState<number>(0);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [summary, setSummary] = useState<PRSummaryRecord | null>(null);
  const [completedActions, setCompletedActions] = useState<Record<number, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!repoId || !prNumber) return;
    try {
      setError(null);

      // Load all repositories for RepoSwitcher
      const reposRes = await fetchApi('/api/repos');
      if (reposRes.status === 401) {
        router.push(`/login?return_to=/repos/${repoId}/pulls/${prNumber}`);
        return;
      }
      if (reposRes.ok) {
        const data = await reposRes.json();
        setAllRepos(data.repositories || []);
      }

      // Load PR details
      const prRes = await fetchApi(`/api/repos/${repoId}/pulls/${prNumber}`);
      if (prRes.status === 401) {
        router.push(`/login?return_to=/repos/${repoId}/pulls/${prNumber}`);
        return;
      }
      if (prRes.status === 404) {
        setError(`Pull Request #${prNumber} was not found or has no scan records.`);
        return;
      }
      if (!prRes.ok) {
        throw new Error('Failed to load pull request scan data');
      }

      const prData = await prRes.json();
      setRepo(prData.repo);
      setLatestScan(prData.latest_scan);
      setNewIssues(prData.new_issues || []);
      setExistingIssuesCount(prData.existing_issues_count || 0);
      setTimeline(prData.timeline || []);
      setSummary(prData.summary || null);
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred');
    } finally {
      setLoading(false);
    }
  }, [repoId, prNumber, router]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const toggleAction = (idx: number) => {
    setCompletedActions(prev => ({
      ...prev,
      [idx]: !prev[idx]
    }));
  };

  const critCount = newIssues.filter(i => i.severity === 'critical').length;
  const highCount = newIssues.filter(i => i.severity === 'high').length;
  const medCount = newIssues.filter(i => i.severity === 'medium').length;
  const lowCount = newIssues.filter(i => i.severity === 'low').length;

  const facts = summary?.facts;
  const actions = facts?.actions || [];
  const categoriesTouched = facts?.categories_touched || [];
  const pushDelta = facts?.delta_since_previous_push;
  const dependencyChanges = facts?.dependency_changes || [];

  return (
    <div className="max-w-[1160px] mx-auto w-full py-4 px-4 sm:px-6 flex flex-col gap-6">
      {/* Header with activeTab="pulls" */}
      <Header
        currentRepo={repo || undefined}
        repositories={allRepos}
        activeTab="pulls"
      />

      {/* Back button */}
      <div className="flex items-center justify-between">
        <Link
          href={`/repos/${repoId}/pulls`}
          className="inline-flex items-center gap-1.5 font-sans font-bold text-sm text-[#14141A] hover:underline"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to pull requests</span>
        </Link>
        <span className="font-mono text-xs text-[#55555F]">
          Pull Request #{prNumber}
        </span>
      </div>

      {loading ? (
        <div className="flex flex-col gap-6">
          <SkeletonStatusCard />
          <SkeletonCard />
        </div>
      ) : error ? (
        <ErrorState
          title="Failed to load pull request details"
          message={error}
          onRetry={loadData}
        />
      ) : latestScan ? (
        <>
          {/* 1. Verdict Banner using StatusCard */}
          <StatusCard
            status={latestScan.status}
            branch={latestScan.branch || 'head'}
            timestamp={latestScan.timestamp}
            critical={critCount}
            high={highCount}
            medium={medCount}
            low={lowCount}
            totalIssues={newIssues.length}
          />

          {/* 2. Executive Reviewer Narrative Card (if present) */}
          {summary?.narrative && (
            <section className="border-2 border-[#14141A] rounded-[18px] bg-white p-5 shadow-[4px_4px_0_#14141A] flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-[#14141A]" />
                  <span className="font-sans font-bold text-xs uppercase tracking-wider text-[#14141A]">
                    Reviewer Executive Summary
                  </span>
                </div>
                <span className="px-2 py-0.5 rounded border border-[#14141A] text-[10px] font-mono font-bold uppercase bg-[#F5F4EE] text-[#55555F]">
                  {summary.narrative_source === 'llm' ? 'AI-Verified' : 'Deterministic'}
                </span>
              </div>
              <p className="font-sans text-sm text-[#14141A] leading-relaxed m-0 font-medium">
                {summary.narrative}
              </p>
            </section>
          )}

          {/* 3. Findings-Delta & Architectural Scope Strip */}
          <section className="border-2 border-[#14141A] rounded-[14px] bg-white p-4 shadow-[3px_3px_0_#14141A] flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3 sm:gap-6 flex-wrap font-mono text-xs font-bold">
              <span className="font-sans font-bold text-xs uppercase tracking-wider text-[#55555F]">
                Scope & Delta:
              </span>
              <span className="text-[#FF6B3D] bg-[#FFD9CC] px-2 py-0.5 rounded border border-[#14141A]">
                +{newIssues.length} new
              </span>
              <span className="text-[#14141A] bg-[#DDF58A] px-2 py-0.5 rounded border border-[#14141A]">
                -{latestScan.fixed_findings_count || 0} fixed
              </span>
              <span className="text-[#55555F] bg-[#F5F4EE] px-2 py-0.5 rounded border border-[#E2E0D6]">
                {existingIssuesCount} baseline
              </span>
              {pushDelta?.previous_head_sha && (
                <span className="text-[#14141A] bg-[#F5F4EE] px-2 py-0.5 rounded border border-[#14141A] text-[11px]">
                  vs {pushDelta.previous_head_sha.slice(0, 7)}: {pushDelta.delta_new >= 0 ? `+${pushDelta.delta_new}` : pushDelta.delta_new} new
                </span>
              )}
            </div>

            {categoriesTouched.length > 0 && (
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="font-sans text-[11px] font-bold text-[#55555F] uppercase">
                  Categories:
                </span>
                {categoriesTouched.map((cat) => (
                  <span
                    key={cat}
                    className="font-mono text-[11px] font-bold px-2 py-0.5 rounded border border-[#14141A] bg-[#F5F4EE] text-[#14141A]"
                  >
                    {cat}
                  </span>
                ))}
              </div>
            )}
          </section>

          {/* 4. 'Needs before merge' Checklist */}
          <section className="border-2 border-[#14141A] rounded-[18px] bg-white p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-4">
            <div className="flex justify-between items-baseline gap-2 flex-wrap">
              <h2 className="text-xl md:text-2xl font-bold font-sans text-[#14141A] m-0">
                Needs Before Merge
              </h2>
              <span className="font-mono text-xs text-[#55555F]">
                {actions.length} action item{actions.length === 1 ? '' : 's'} required
              </span>
            </div>

            {actions.length === 0 ? (
              <div className="p-6 text-center bg-[#F6FBDD] border-2 border-[#14141A] rounded-[14px] flex items-center justify-center gap-3">
                <ShieldCheck className="w-5 h-5 text-[#14141A]" />
                <p className="font-sans font-bold text-sm text-[#14141A] m-0">
                  All security gates passed — zero blocking actions required before merge.
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-2.5">
                {actions.map((act, idx) => {
                  const isChecked = !!completedActions[idx];
                  return (
                    <div
                      key={idx}
                      onClick={() => toggleAction(idx)}
                      className={`p-3.5 border-2 border-[#14141A] rounded-[12px] flex items-start gap-3 transition-colors cursor-pointer select-none ${
                        isChecked ? 'bg-[#F6FBDD] opacity-75' : 'bg-[#F5F4EE] hover:bg-[#EAE8DD]'
                      }`}
                    >
                      <button
                        type="button"
                        aria-label={`Mark "${act.title}" as complete`}
                        className="mt-0.5 text-[#14141A] shrink-0"
                      >
                        {isChecked ? (
                          <CheckSquare className="w-5 h-5 text-[#14141A]" />
                        ) : (
                          <Square className="w-5 h-5 text-[#14141A]" />
                        )}
                      </button>

                      <div className="flex flex-col gap-0.5 text-left flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`font-sans font-bold text-sm text-[#14141A] ${isChecked ? 'line-through text-[#55555F]' : ''}`}>
                            {act.title}
                          </span>
                          {act.file && act.line && (
                            <a
                              href={`#finding-${act.fingerprint || `${act.file}-${act.line}`}`}
                              onClick={(e) => e.stopPropagation()}
                              className="font-mono text-xs text-[#FF6B3D] underline font-bold"
                            >
                              Jump to finding →
                            </a>
                          )}
                        </div>
                        <p className="font-sans text-xs text-[#55555F] m-0">
                          {act.description}
                        </p>
                      </div>
                    </div>
                  );
                })}

                {facts && facts.omitted_actions_count > 0 && (
                  <p className="font-sans text-xs text-[#55555F] font-bold mt-1">
                    * ... and {facts.omitted_actions_count} additional action item(s) capped for review focus.
                  </p>
                )}
              </div>
            )}
          </section>

          {/* 5. Dependency Changes (if any) */}
          {dependencyChanges.length > 0 && (
            <section className="border-2 border-[#14141A] rounded-[18px] bg-white p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-4">
              <div className="flex justify-between items-baseline gap-2 flex-wrap">
                <h2 className="text-xl md:text-2xl font-bold font-sans text-[#14141A] m-0">
                  Dependency Changes
                </h2>
                <span className="font-mono text-xs text-[#55555F]">
                  {dependencyChanges.length} package{dependencyChanges.length === 1 ? '' : 's'} modified
                </span>
              </div>

              <div className="border-2 border-[#14141A] rounded-[12px] overflow-x-auto">
                <table className="w-full text-left font-sans text-xs border-collapse">
                  <thead>
                    <tr className="bg-[#14141A] text-white font-mono uppercase text-[10px]">
                      <th className="p-2.5">Ecosystem</th>
                      <th className="p-2.5">Package</th>
                      <th className="p-2.5">Change</th>
                      <th className="p-2.5">Version</th>
                      <th className="p-2.5">Previous</th>
                      <th className="p-2.5">Manifest</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y-2 divide-[#14141A]">
                    {dependencyChanges.map((dep, dIdx) => (
                      <tr key={dIdx} className="bg-white hover:bg-[#F5F4EE]">
                        <td className="p-2.5 font-bold uppercase">{dep.ecosystem}</td>
                        <td className="p-2.5 font-mono font-bold text-[#14141A]">{dep.name}</td>
                        <td className="p-2.5">
                          <span className={`px-2 py-0.5 rounded border border-[#14141A] text-[10px] font-mono font-bold uppercase ${
                            dep.change_type === 'added' ? 'bg-[#FFD9CC] text-[#FF6B3D]' :
                            dep.change_type === 'removed' ? 'bg-[#DDF58A] text-[#14141A]' :
                            'bg-[#F5F4EE] text-[#14141A]'
                          }`}>
                            {dep.change_type}
                          </span>
                        </td>
                        <td className="p-2.5 font-mono">{dep.version || '—'}</td>
                        <td className="p-2.5 font-mono text-[#55555F]">{dep.previous_version || '—'}</td>
                        <td className="p-2.5 font-mono text-xs text-[#55555F]">{dep.manifest_file}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* 6. New Findings as FindingRows */}
          <section className="border-2 border-[#14141A] rounded-[18px] bg-white p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-4">
            <div className="flex justify-between items-baseline gap-2 flex-wrap">
              <h2 className="text-xl md:text-2xl font-bold font-sans text-[#14141A] m-0">
                New Findings in this PR
              </h2>
              <span className="font-mono text-xs text-[#55555F]">
                {newIssues.length} finding{newIssues.length === 1 ? '' : 's'} introduced
              </span>
            </div>

            {newIssues.length === 0 ? (
              <div className="p-8 text-center bg-[#F5F4EE] border-2 border-[#14141A] rounded-[14px]">
                <p className="font-sans font-bold text-sm text-[#14141A] m-0">
                  Zero new security issues introduced in this pull request diff.
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {newIssues.map((issue) => (
                  <div
                    key={issue.id}
                    id={`finding-${issue.fingerprint || `${issue.filepath}-${issue.line_number}`}`}
                    className="border-2 border-[#14141A] rounded-[14px] bg-white shadow-[3px_3px_0_#14141A] overflow-hidden"
                  >
                    <details className="group" open={issue.severity === 'critical' || issue.severity === 'high'}>
                      <summary className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-4 select-none cursor-pointer list-none relative">
                        <div className="flex flex-wrap items-center gap-3">
                          <Chip
                            label={issue.severity.toUpperCase()}
                            variant={issue.severity}
                          />
                          <div className="text-left">
                            <span className="font-sans font-bold text-sm text-[#14141A] mr-2">
                              {issue.fix_title || issue.rule_id}
                            </span>
                            <span className="font-mono text-xs text-[#55555F] break-all">
                              {issue.filepath}:{issue.line_number}
                            </span>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 font-mono text-xs text-[#55555F] pr-6 md:pr-8">
                          <span className="px-2 py-0.5 rounded border border-[#14141A] text-[10px] font-bold uppercase bg-[#F5F4EE] text-[#14141A]">
                            {issue.scanner}
                          </span>
                          <span>{issue.rule_id}</span>
                        </div>

                        <span className="absolute right-4 top-1/2 -translate-y-1/2 transition-transform duration-200 group-open:rotate-180">
                          <ChevronDown className="w-4 h-4 text-[#14141A]" />
                        </span>
                      </summary>

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
                              Target Code Snippet
                            </span>
                            <pre className="bg-[#14141A] text-[#D6F25B] p-3 rounded-[10px] border-2 border-[#14141A] overflow-x-auto font-mono text-xs leading-relaxed m-0 max-w-full">
                              <code>{issue.code_snippet}</code>
                            </pre>
                          </div>
                        )}

                        {(issue.fix_before || issue.fix_after) && (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-1">
                            {issue.fix_before && (
                              <div className="flex flex-col gap-1">
                                <div className="font-sans font-bold text-[11px] text-[#FF6B3D] flex items-center gap-1">
                                  <XCircle className="w-3.5 h-3.5" /> Vulnerable Code
                                </div>
                                <pre className="bg-[#FFD9CC] border-2 border-[#14141A] text-[#14141A] p-2.5 rounded-[10px] font-mono text-xs overflow-x-auto m-0 font-bold max-w-full">
                                  <code>{issue.fix_before}</code>
                                </pre>
                              </div>
                            )}
                            {issue.fix_after && (
                              <div className="flex flex-col gap-1">
                                <div className="font-sans font-bold text-[11px] text-[#14141A] flex items-center gap-1">
                                  <CheckCircle className="w-3.5 h-3.5 text-[#14141A]" /> Remediation Fix
                                </div>
                                <pre className="bg-[#DDF58A] border-2 border-[#14141A] text-[#14141A] p-2.5 rounded-[10px] font-mono text-xs overflow-x-auto m-0 font-bold max-w-full">
                                  <code>{issue.fix_after}</code>
                                </pre>
                              </div>
                            )}
                          </div>
                        )}

                        {issue.doc_url && (
                          <div className="flex justify-end pt-1">
                            <a
                              href={issue.doc_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 font-sans font-bold text-xs text-[#14141A] hover:underline"
                            >
                              <span>Official advisory docs</span>
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
          </section>

          {/* 7. Push-by-Push Timeline */}
          <section className="border-2 border-[#14141A] rounded-[18px] bg-white p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-3">
            <h2 className="text-xl md:text-2xl font-bold font-sans text-[#14141A] m-0">
              Push-by-Push Timeline
            </h2>

            <div className="flex flex-col divide-y-2 divide-[#E2E0D6]">
              {timeline.map((item) => {
                const rawV = (item.verdict || 'safe').toLowerCase();
                const verdictVariant =
                  rawV === 'block'
                    ? 'block'
                    : rawV === 'review' || rawV === 'attention'
                    ? 'attention'
                    : 'safe';

                return (
                  <div
                    key={item.id}
                    className="py-3 flex items-center justify-between gap-3 flex-wrap"
                  >
                    <div className="flex items-center gap-3 flex-wrap min-w-[200px]">
                      <span className="font-mono text-xs text-[#14141A] font-bold">
                        {item.commit_sha ? item.commit_sha.slice(0, 7) : 'head'}
                      </span>
                      <span className="font-mono text-xs text-[#55555F]">
                        {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {new Date(item.timestamp).toLocaleDateString()}
                      </span>
                      <Chip label={item.verdict ? item.verdict.toUpperCase() : 'SAFE'} variant={verdictVariant} />
                    </div>

                    <Link
                      href={`/results?scan_id=${item.id}`}
                      className="font-sans text-xs font-bold text-[#14141A] hover:underline"
                    >
                      View Report →
                    </Link>
                  </div>
                );
              })}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
