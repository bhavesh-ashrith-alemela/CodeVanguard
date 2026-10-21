'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Shield } from 'lucide-react';
import { Header, EmptyState, SkeletonCard, ErrorState } from '@/components/ui';
import { fetchApi, Repository } from '@/lib/api';

export default function DashboardPage() {
  const router = useRouter();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [appSlug, setAppSlug] = useState('codevanguard');

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const envSlug = process.env.NEXT_PUBLIC_GITHUB_APP_SLUG;
      if (envSlug) setAppSlug(envSlug);

      const res = await fetchApi('/api/repos');
      if (res.status === 401) {
        router.push('/login?return_to=/dashboard');
        return;
      }
      if (!res.ok) {
        throw new Error('Failed to load repositories');
      }

      const data = await res.json();
      const repos: Repository[] = data.repositories || [];
      setRepositories(repos);

      // If repositories exist, navigate directly to the first repo overview
      if (repos.length > 0) {
        router.replace(`/repos/${repos[0].id}`);
      }
    } catch (err: any) {
      setError(err.message || 'Unable to connect to service');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const installUrl = `https://github.com/apps/${appSlug}/installations/new`;

  return (
    <div className="max-w-[1160px] mx-auto w-full py-4 px-4 sm:px-6 flex flex-col gap-6">
      {/* Header */}
      <Header />

      {/* States */}
      {loading ? (
        <div className="flex flex-col gap-4">
          <SkeletonCard />
        </div>
      ) : error ? (
        <ErrorState
          title="Failed to load repositories"
          message={error}
          onRetry={loadData}
        />
      ) : repositories.length === 0 ? (
        /* First run (no installation): an EmptyState with a single 'Install the GitHub App' action */
        <EmptyState
          icon={<Shield className="w-7 h-7" />}
          title="No repositories connected"
          description="Install the CodeVanguard GitHub App to choose repositories for automated pull request scans and static security testing."
          actionLabel="Install the GitHub App"
          actionHref={installUrl}
          external={true}
        />
      ) : null}
    </div>
  );
}
