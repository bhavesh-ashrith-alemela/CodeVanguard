'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { GitPullRequest } from 'lucide-react';
import { 
  Header, Chip, SkeletonCard, ErrorState, EmptyState 
} from '@/components/ui';
import { fetchApi, Repository } from '@/lib/api';

interface PullRequestSummary {
  pr_number: number;
  title: string;
  branch: string;
  commit_sha: string;
  status: string;
  verdict: 'BLOCK' | 'REVIEW' | 'SAFE';
  new_findings_count: number;
  fixed_findings_count: number;
  existing_findings_count: number;
  timestamp: string;
  latest_scan_id: string;
}

export default function RepoPullsPage() {
  const params = useParams();
  const router = useRouter();
  const repoId = params.id as string;

  const [allRepos, setAllRepos] = useState<Repository[]>([]);
  const [repo, setRepo] = useState<Repository | null>(null);
  const [pullRequests, setPullRequests] = useState<PullRequestSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!repoId) return;
    try {
      setError(null);

      // Load all repositories for RepoSwitcher
      const reposRes = await fetchApi('/api/repos');
      if (reposRes.status === 401) {
        router.push(`/login?return_to=/repos/${repoId}/pulls`);
        return;
      }
      if (reposRes.ok) {
        const data = await reposRes.json();
        setAllRepos(data.repositories || []);
      }

      // Load repository details
      const repoRes = await fetchApi(`/api/repos/${repoId}`);
      if (repoRes.status === 401) {
        router.push(`/login?return_to=/repos/${repoId}/pulls`);
        return;
      }
      if (repoRes.status === 404) {
        setError('Repository not found or disconnected.');
        return;
      }
      if (!repoRes.ok) {
        throw new Error('Failed to load repository details');
      }
      const repoData = await repoRes.json();
      setRepo(repoData.repository);

      // Load pull requests
      const pullsRes = await fetchApi(`/api/repos/${repoId}/pulls`);
      if (pullsRes.ok) {
        const pullsData = await pullsRes.json();
        setPullRequests(pullsData.pull_requests || []);
      }
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred');
    } finally {
      setLoading(false);
    }
  }, [repoId, router]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <div className="max-w-[1160px] mx-auto w-full py-4 px-4 sm:px-6 flex flex-col gap-6">
      {/* Header with activeTab="pulls" */}
      <Header
        currentRepo={repo || undefined}
        repositories={allRepos}
        activeTab="pulls"
      />

      {loading ? (
        <div className="flex flex-col gap-3">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : error ? (
        <ErrorState
          title="Failed to load pull requests"
          message={error}
          onRetry={loadData}
        />
      ) : pullRequests.length === 0 ? (
        <EmptyState
          icon={<GitPullRequest className="w-7 h-7" />}
          title="No pull requests analyzed yet"
          description="Submit or synchronize a pull request on GitHub to trigger diff-aware static application security scans."
        />
      ) : (
        <section className="border-2 border-[#14141A] rounded-[18px] bg-white p-6 shadow-[5px_5px_0_#14141A] flex flex-col gap-2">
          <h2 className="text-xl md:text-2xl font-bold font-sans text-[#14141A] mb-2 m-0">
            Pull requests
          </h2>

          <div className="flex flex-col divide-y-2 divide-[#E2E0D6]">
            {pullRequests.map((pr) => {
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
                  className="py-3.5 flex items-center justify-between gap-3 flex-wrap hover:bg-[#F5F4EE] px-2 rounded-[10px] transition-colors"
                >
                  <div className="flex-1 min-w-[200px]">
                    <div className="font-sans font-medium text-sm text-[#14141A]">
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
        </section>
      )}
    </div>
  );
}
