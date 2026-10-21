'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Shield, RefreshCw } from 'lucide-react';
import { Header, EmptyState, SkeletonCard, ErrorState } from '@/components/ui';
import { fetchApi, Repository } from '@/lib/api';

export default function DashboardPage() {
  const router = useRouter();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [installUrl, setInstallUrl] = useState('https://github.com/apps/codevanguard/installations/new');

  const loadData = async (triggerSync = false) => {
    setLoading(true);
    setError(null);
    try {
      const endpoint = triggerSync ? '/api/repos?sync=true' : '/api/repos';
      const res = await fetchApi(endpoint);
      if (res.status === 401) {
        router.push('/login?return_to=/dashboard');
        return;
      }
      if (!res.ok) {
        throw new Error('Failed to load repositories');
      }

      const data = await res.json();
      if (data.install_url) {
        setInstallUrl(data.install_url);
      } else if (data.app_slug) {
        setInstallUrl(`https://github.com/apps/${data.app_slug}/installations/new`);
      }

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

  const handleManualSync = async () => {
    setSyncing(true);
    try {
      const res = await fetchApi('/api/repos/sync', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        const repos: Repository[] = data.repositories || [];
        setRepositories(repos);
        if (repos.length > 0) {
          router.replace(`/repos/${repos[0].id}`);
        }
      }
    } catch (e) {
      // Ignore
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

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
          onRetry={() => loadData(true)}
        />
      ) : repositories.length === 0 ? (
        <div className="flex flex-col items-center gap-4">
          <EmptyState
            icon={<Shield className="w-7 h-7" />}
            title="No repositories connected"
            description="Install the CodeVanguard GitHub App to choose repositories for automated pull request scans and static security testing."
            actionLabel="Install GitHub App"
            actionHref={installUrl}
            external={true}
          />
          <button
            onClick={handleManualSync}
            disabled={syncing}
            className="inline-flex items-center gap-2 px-5 py-2.5 border-2 border-[#14141A] rounded-full bg-white text-[#14141A] font-mono text-xs font-bold hover:bg-[#F5F4EE] transition-all shadow-[3px_3px_0_#14141A] active:translate-x-0.5 active:translate-y-0.5 active:shadow-none cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
            {syncing ? 'Checking GitHub Installations...' : 'Already Installed? Sync Repositories'}
          </button>
        </div>
      ) : null}
    </div>
  );
}

