'use client';

import React, { useState, useEffect, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { 
  Shield, RefreshCw, Plus, Search, Lock, Globe, GitBranch, 
  ExternalLink, CheckCircle2, AlertCircle, ArrowRight, Link2, X
} from 'lucide-react';
import { Header, SkeletonCard, ErrorState } from '@/components/ui';
import { fetchApi, Repository, GitHubUserRepo } from '@/lib/api';

function DashboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [installUrl, setInstallUrl] = useState<string | null>(null);
  const [appSlug, setAppSlug] = useState<string | null>(null);

  // Connect Repository state
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [connectTab, setConnectTab] = useState<'url' | 'github' | 'app'>('url');
  const [repoUrl, setRepoUrl] = useState('');
  const [repoBranch, setRepoBranch] = useState('');
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [connectSuccess, setConnectSuccess] = useState<string | null>(null);

  // User's GitHub Repositories
  const [userGhRepos, setUserGhRepos] = useState<GitHubUserRepo[]>([]);
  const [loadingGhRepos, setLoadingGhRepos] = useState(false);
  const [ghFilter, setGhFilter] = useState('');
  const [connectingId, setConnectingId] = useState<number | null>(null);
  const [authWithGithub, setAuthWithGithub] = useState<boolean>(true);

  // Local repo search filter
  const [repoSearch, setRepoSearch] = useState('');

  // Scanning state per repo
  const [triggeringScanId, setTriggeringScanId] = useState<string | null>(null);

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
      setAppSlug(data.app_slug || null);
      if (data.install_url) {
        setInstallUrl(data.install_url);
      } else {
        setInstallUrl(null);
      }

      const repos: Repository[] = data.repositories || [];
      setRepositories(repos);
    } catch (err: any) {
      setError(err.message || 'Unable to connect to service');
    } finally {
      setLoading(false);
    }
  };

  const loadUserGhRepos = async () => {
    setLoadingGhRepos(true);
    try {
      const res = await fetchApi('/api/repos/github-list');
      if (res.ok) {
        const data = await res.json();
        setUserGhRepos(data.repositories || []);
        setAuthWithGithub(data.authenticated_with_github !== false);
      }
    } catch {
      // Ignored
    } finally {
      setLoadingGhRepos(false);
    }
  };

  useEffect(() => {
    loadData();
    if (searchParams.get('connect') === 'true') {
      setShowConnectModal(true);
    }
  }, [searchParams]);

  useEffect(() => {
    if (connectTab === 'github' && userGhRepos.length === 0) {
      loadUserGhRepos();
    }
  }, [connectTab]);

  const handleManualSync = async () => {
    setSyncing(true);
    try {
      const res = await fetchApi('/api/repos/sync', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        const repos: Repository[] = data.repositories || [];
        setRepositories(repos);
        if (data.install_url) {
          setInstallUrl(data.install_url);
        }
      }
    } catch {
      // Ignore
    } finally {
      setSyncing(false);
    }
  };

  const handleConnectByUrl = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const cleanUrl = repoUrl.trim();
    if (!cleanUrl) {
      setConnectError('Please enter a GitHub repository URL or identifier.');
      return;
    }

    setIsConnecting(true);
    setConnectError(null);
    setConnectSuccess(null);

    try {
      const res = await fetchApi('/api/repos/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: cleanUrl,
          branch: repoBranch.trim() || undefined
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to connect repository.');
      }

      setConnectSuccess(`Repository '${data.repository?.full_name || cleanUrl}' connected successfully!`);
      setRepoUrl('');
      setRepoBranch('');

      // Refresh repositories and redirect to repo overview
      await loadData();
      if (data.repository?.id) {
        setTimeout(() => {
          router.push(`/repos/${data.repository.id}`);
        }, 600);
      }
    } catch (err: any) {
      setConnectError(err.message || 'Error connecting repository.');
    } finally {
      setIsConnecting(false);
    }
  };

  const handleConnectGhRepo = async (ghRepo: GitHubUserRepo) => {
    setConnectingId(ghRepo.id);
    setConnectError(null);

    try {
      const res = await fetchApi('/api/repos/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: ghRepo.full_name,
          branch: ghRepo.default_branch
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to connect repository.');
      }

      await loadData();
      if (data.repository?.id) {
        router.push(`/repos/${data.repository.id}`);
      }
    } catch (err: any) {
      alert(err.message || 'Error connecting repository.');
    } finally {
      setConnectingId(null);
    }
  };

  const handleQuickScan = async (repo: Repository) => {
    setTriggeringScanId(repo.id);
    try {
      const res = await fetchApi(`/api/repos/${repo.id}/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ branch: repo.default_branch || 'main' })
      });
      const data = await res.json();
      if (res.ok && data.scan_id) {
        router.push(`/repos/${repo.id}`);
      } else {
        alert(data.detail || 'Failed to trigger scan');
      }
    } catch (err: any) {
      alert(err.message || 'Failed to trigger scan');
    } finally {
      setTriggeringScanId(null);
    }
  };

  const formatTimeAgo = (timestamp?: string | null) => {
    if (!timestamp) return 'Never scanned';
    try {
      const date = new Date(timestamp);
      const diffMs = Date.now() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 1) return 'just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      const diffDays = Math.floor(diffHours / 24);
      return `${diffDays}d ago`;
    } catch {
      return timestamp;
    }
  };

  const filteredRepositories = repositories.filter(r =>
    r.full_name.toLowerCase().includes(repoSearch.toLowerCase().trim())
  );

  const filteredGhRepos = userGhRepos.filter(r =>
    r.full_name.toLowerCase().includes(ghFilter.toLowerCase().trim()) ||
    (r.description && r.description.toLowerCase().includes(ghFilter.toLowerCase().trim()))
  );

  return (
    <div className="max-w-[1160px] mx-auto w-full py-4 px-4 sm:px-6 flex flex-col gap-6">
      <Header />

      {/* Top Banner & Action Bar */}
      <div className="flex items-center justify-between gap-4 flex-wrap pb-2 border-b-2 border-[#14141A]">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black text-[#14141A] tracking-tight">
            Repositories
          </h1>
          <p className="font-sans text-xs text-[#55555F] mt-1">
            Connect and manage GitHub repositories for automated SAST &amp; secret scanning.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => handleManualSync()}
            disabled={syncing}
            title="Sync installations from GitHub"
            className="p-2 border-2 border-[#14141A] rounded-full bg-white hover:bg-[#F5F4EE] transition-all shadow-[2px_2px_0_#14141A] active:translate-x-0.5 active:translate-y-0.5 active:shadow-none cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 text-[#14141A] ${syncing ? 'animate-spin' : ''}`} />
          </button>

          <button
            onClick={() => {
              setShowConnectModal(!showConnectModal);
              setConnectError(null);
              setConnectSuccess(null);
            }}
            className="inline-flex items-center gap-2 px-5 py-2.5 border-2 border-[#14141A] rounded-full bg-[#D6F25B] text-[#14141A] font-bold text-xs shadow-[3px_3px_0_#14141A] hover:bg-[#c6e448] active:translate-x-0.5 active:translate-y-0.5 active:shadow-none transition-all cursor-pointer"
          >
            {showConnectModal ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
            <span>{showConnectModal ? 'Close Form' : 'Connect Repository'}</span>
          </button>
        </div>
      </div>

      {/* Loading & Error States */}
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
      ) : null}

      {/* Connect Repository Section (Always shown if 0 repos, or toggled via button) */}
      {!loading && !error && (repositories.length === 0 || showConnectModal) && (
        <div className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] p-6 sm:p-8 flex flex-col gap-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1.5">
              <div className="inline-flex items-center gap-2 self-start px-2.5 py-0.5 rounded-full border border-[#14141A] bg-[#B8A2FF] font-mono text-[10px] font-bold text-[#14141A]">
                <span>IMPORT GIT REPOSITORY</span>
              </div>
              <h2 className="text-xl sm:text-2xl font-black text-[#14141A]">
                Connect your GitHub repository
              </h2>
              <p className="font-sans text-xs text-[#55555F]">
                Insert your repository link to connect directly (like Vercel or Render), or import from your GitHub account.
              </p>
            </div>

            {repositories.length > 0 && (
              <button
                onClick={() => setShowConnectModal(false)}
                className="p-1.5 rounded-full hover:bg-[#F5F4EE] border border-[#14141A] cursor-pointer"
                aria-label="Close"
              >
                <X className="w-4 h-4 text-[#14141A]" />
              </button>
            )}
          </div>

          {/* Mode Switcher Tabs */}
          <div className="flex items-center gap-2 border-b-2 border-[#E2E0D6] pb-3 flex-wrap">
            <button
              onClick={() => { setConnectTab('url'); setConnectError(null); }}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-full font-mono text-xs font-bold transition-all cursor-pointer ${
                connectTab === 'url'
                  ? 'bg-[#14141A] text-[#F5F4EE] shadow-[2px_2px_0_#D6F25B]'
                  : 'bg-white text-[#14141A] border border-[#14141A] hover:bg-[#F5F4EE]'
              }`}
            >
              <Link2 className="w-3.5 h-3.5" />
              <span>Insert Repo Link</span>
            </button>

            <button
              onClick={() => { setConnectTab('github'); setConnectError(null); }}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-full font-mono text-xs font-bold transition-all cursor-pointer ${
                connectTab === 'github'
                  ? 'bg-[#14141A] text-[#F5F4EE] shadow-[2px_2px_0_#D6F25B]'
                  : 'bg-white text-[#14141A] border border-[#14141A] hover:bg-[#F5F4EE]'
              }`}
            >
              <GitBranch className="w-3.5 h-3.5" />
              <span>Your GitHub Repos</span>
            </button>

            <button
              onClick={() => { setConnectTab('app'); setConnectError(null); }}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-full font-mono text-xs font-bold transition-all cursor-pointer ${
                connectTab === 'app'
                  ? 'bg-[#14141A] text-[#F5F4EE] shadow-[2px_2px_0_#D6F25B]'
                  : 'bg-white text-[#14141A] border border-[#14141A] hover:bg-[#F5F4EE]'
              }`}
            >
              <Shield className="w-3.5 h-3.5" />
              <span>GitHub App (Optional)</span>
            </button>
          </div>

          {/* TAB 1: Insert Repo Link */}
          {connectTab === 'url' && (
            <form onSubmit={handleConnectByUrl} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <label className="font-mono text-xs font-bold text-[#14141A] flex items-center gap-1.5">
                  <Globe className="w-3.5 h-3.5 text-[#55555F]" />
                  <span>GitHub Repository Link or Path</span>
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    placeholder="https://github.com/owner/repository  or  owner/repository"
                    disabled={isConnecting}
                    className="w-full pl-4 pr-4 py-3 border-2 border-[#14141A] rounded-xl font-mono text-xs sm:text-sm bg-[#FAF9F5] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#D6F25B] transition-all"
                  />
                </div>
                <span className="font-mono text-[11px] text-[#55555F]">
                  Supports public repositories or private repositories in your authorized GitHub account.
                </span>
              </div>

              <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-end">
                <div className="flex-1 flex flex-col gap-2 w-full sm:w-auto">
                  <label className="font-mono text-xs font-bold text-[#14141A] flex items-center gap-1.5">
                    <GitBranch className="w-3.5 h-3.5 text-[#55555F]" />
                    <span>Default Branch (Optional)</span>
                  </label>
                  <input
                    type="text"
                    value={repoBranch}
                    onChange={(e) => setRepoBranch(e.target.value)}
                    placeholder="main (leave blank to auto-detect)"
                    disabled={isConnecting}
                    className="w-full px-4 py-2.5 border-2 border-[#14141A] rounded-xl font-mono text-xs bg-[#FAF9F5] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#D6F25B] transition-all"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isConnecting || !repoUrl.trim()}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-2.5 border-2 border-[#14141A] rounded-xl bg-[#D6F25B] text-[#14141A] font-bold text-sm shadow-[3px_3px_0_#14141A] hover:bg-[#c6e448] disabled:opacity-50 disabled:cursor-not-allowed active:translate-x-0.5 active:translate-y-0.5 active:shadow-none transition-all cursor-pointer"
                >
                  {isConnecting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Verifying &amp; Connecting...</span>
                    </>
                  ) : (
                    <>
                      <Plus className="w-4 h-4" />
                      <span>Connect Repository</span>
                    </>
                  )}
                </button>
              </div>

              {connectError && (
                <div className="flex items-center gap-2.5 p-3 rounded-xl border-2 border-[#FF6B3D] bg-[#FFF2EE] text-[#14141A] font-mono text-xs font-bold">
                  <AlertCircle className="w-4 h-4 text-[#FF6B3D] flex-shrink-0" />
                  <span>{connectError}</span>
                </div>
              )}

              {connectSuccess && (
                <div className="flex items-center gap-2.5 p-3 rounded-xl border-2 border-[#14141A] bg-[#F6FBDD] text-[#14141A] font-mono text-xs font-bold">
                  <CheckCircle2 className="w-4 h-4 text-[#00B894] flex-shrink-0" />
                  <span>{connectSuccess}</span>
                </div>
              )}
            </form>
          )}

          {/* TAB 2: Select from GitHub */}
          {connectTab === 'github' && (
            <div className="flex flex-col gap-4">
              {!authWithGithub ? (
                <div className="flex flex-col items-center justify-center py-8 gap-3 text-center">
                  <Shield className="w-8 h-8 text-[#55555F]" />
                  <p className="font-sans text-xs text-[#55555F] max-w-md">
                    Connect your GitHub account to view and import your repositories directly with 1-click.
                  </p>
                  <Link
                    href="/login?return_to=/dashboard?connect=true"
                    className="inline-flex items-center gap-2 px-5 py-2.5 border-2 border-[#14141A] rounded-full bg-[#14141A] text-white font-bold text-xs shadow-[3px_3px_0_#D6F25B]"
                  >
                    <span>Connect GitHub Account</span>
                  </Link>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between gap-4 flex-wrap">
                    <div className="relative flex-1 min-w-[200px]">
                      <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#55555F]" />
                      <input
                        type="text"
                        value={ghFilter}
                        onChange={(e) => setGhFilter(e.target.value)}
                        placeholder="Search your GitHub repositories..."
                        className="w-full pl-9 pr-4 py-2 border-2 border-[#14141A] rounded-full font-mono text-xs bg-[#FAF9F5] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#D6F25B]"
                      />
                    </div>
                    <button
                      onClick={() => loadUserGhRepos()}
                      disabled={loadingGhRepos}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-[#14141A] rounded-full font-mono text-xs font-bold hover:bg-[#F5F4EE] cursor-pointer"
                    >
                      <RefreshCw className={`w-3 h-3 ${loadingGhRepos ? 'animate-spin' : ''}`} />
                      <span>Refresh</span>
                    </button>
                  </div>

                  {loadingGhRepos ? (
                    <div className="py-8 text-center font-mono text-xs text-[#55555F] flex items-center justify-center gap-2">
                      <RefreshCw className="w-4 h-4 animate-spin text-[#14141A]" />
                      <span>Loading your GitHub repositories...</span>
                    </div>
                  ) : filteredGhRepos.length === 0 ? (
                    <div className="py-8 text-center font-mono text-xs text-[#55555F]">
                      {userGhRepos.length === 0
                        ? 'No repositories found for your account. You can paste any repository URL in the "Insert Repo Link" tab.'
                        : 'No matching repositories found.'}
                    </div>
                  ) : (
                    <div className="max-h-72 overflow-y-auto flex flex-col gap-2 pr-1">
                      {filteredGhRepos.map((ghRepo) => (
                        <div
                          key={ghRepo.id}
                          className="flex items-center justify-between gap-3 p-3 border-2 border-[#14141A] rounded-xl bg-white hover:bg-[#FAF9F5] transition-colors"
                        >
                          <div className="flex items-start gap-2.5 min-w-0">
                            {ghRepo.private ? (
                              <Lock className="w-4 h-4 text-[#14141A] mt-0.5 flex-shrink-0" />
                            ) : (
                              <Globe className="w-4 h-4 text-[#55555F] mt-0.5 flex-shrink-0" />
                            )}
                            <div className="min-w-0 flex flex-col">
                              <span className="font-mono text-xs font-bold text-[#14141A] truncate">
                                {ghRepo.full_name}
                              </span>
                              {ghRepo.description && (
                                <span className="font-sans text-[11px] text-[#55555F] truncate max-w-sm">
                                  {ghRepo.description}
                                </span>
                              )}
                              <span className="font-mono text-[10px] text-[#888891] mt-0.5">
                                Branch: {ghRepo.default_branch}
                              </span>
                            </div>
                          </div>

                          <div>
                            {ghRepo.connected ? (
                              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-[#14141A] bg-[#F6FBDD] font-mono text-[11px] font-bold text-[#14141A]">
                                <CheckCircle2 className="w-3.5 h-3.5 text-[#00B894]" />
                                <span>Connected</span>
                              </div>
                            ) : (
                              <button
                                onClick={() => handleConnectGhRepo(ghRepo)}
                                disabled={connectingId === ghRepo.id}
                                className="inline-flex items-center gap-1.5 px-4 py-1.5 border-2 border-[#14141A] rounded-full bg-[#D6F25B] text-[#14141A] font-mono text-xs font-bold hover:bg-[#c6e448] disabled:opacity-50 cursor-pointer shadow-[2px_2px_0_#14141A] active:translate-x-0.5 active:translate-y-0.5 active:shadow-none"
                              >
                                {connectingId === ghRepo.id ? (
                                  <RefreshCw className="w-3 h-3 animate-spin" />
                                ) : (
                                  <Plus className="w-3 h-3" />
                                )}
                                <span>Import</span>
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* TAB 3: GitHub App (Optional) */}
          {connectTab === 'app' && (
            <div className="flex flex-col gap-4">
              <div className="border border-[#14141A] rounded-xl p-4 bg-[#FAF9F5] flex flex-col gap-2">
                <span className="font-mono text-xs font-bold text-[#14141A] uppercase tracking-wider">
                  Automated Pull Request Scanning
                </span>
                <p className="font-sans text-xs text-[#55555F] leading-relaxed">
                  Installing the CodeVanguard GitHub App connects webhooks so CodeVanguard automatically runs SAST checks on every commit, PR push, and generates inline review summaries.
                </p>
              </div>

              <div className="flex flex-col sm:flex-row items-center gap-3 pt-1">
                {installUrl ? (
                  <a
                    href={installUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 px-6 py-2.5 border-2 border-[#14141A] rounded-full bg-[#14141A] text-white font-bold text-xs shadow-[3px_3px_0_#D6F25B] hover:bg-[#2B2B36] cursor-pointer"
                  >
                    <span>Install GitHub App</span>
                    <ExternalLink className="w-3.5 h-3.5 text-[#D6F25B]" />
                  </a>
                ) : (
                  <div className="flex flex-col gap-1 w-full p-3 rounded-xl border border-[#E2E0D6] bg-white font-mono text-xs text-[#55555F]">
                    <span className="font-bold text-[#14141A]">GitHub App slug is not configured</span>
                    <span>Direct repository connection (Tabs 1 &amp; 2) is active and requires no GitHub App setup. If you created a GitHub App, set <code className="bg-[#FAF9F5] px-1 py-0.5 rounded font-bold">GITHUB_APP_SLUG</code> in your environment.</span>
                  </div>
                )}

                <button
                  onClick={handleManualSync}
                  disabled={syncing}
                  className="inline-flex items-center gap-2 px-5 py-2.5 border-2 border-[#14141A] rounded-full bg-white text-[#14141A] font-mono text-xs font-bold hover:bg-[#F5F4EE] shadow-[3px_3px_0_#14141A] active:translate-x-0.5 active:translate-y-0.5 active:shadow-none cursor-pointer"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
                  <span>{syncing ? 'Checking Installations...' : 'Already Installed? Sync Repos'}</span>
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Connected Repositories Grid */}
      {!loading && !error && repositories.length > 0 && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <span className="font-mono text-xs font-bold text-[#55555F]">
              Showing {filteredRepositories.length} of {repositories.length} repository{repositories.length !== 1 ? 'ies' : ''}
            </span>

            {repositories.length > 3 && (
              <div className="relative w-full sm:w-64">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#55555F]" />
                <input
                  type="text"
                  value={repoSearch}
                  onChange={(e) => setRepoSearch(e.target.value)}
                  placeholder="Filter connected repositories..."
                  className="w-full pl-9 pr-3 py-1.5 border-2 border-[#14141A] rounded-full font-mono text-xs bg-white focus:outline-none focus:ring-2 focus:ring-[#D6F25B]"
                />
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredRepositories.map((repo) => {
              const latest = repo.latest_scan;
              const isTriggering = triggeringScanId === repo.id;

              return (
                <div
                  key={repo.id}
                  className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[4px_4px_0_#14141A] hover:shadow-[6px_6px_0_#14141A] transition-all p-5 flex flex-col justify-between gap-4"
                >
                  {/* Repo Header */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2.5 min-w-0">
                      {repo.is_private ? (
                        <span title="Private repository" className="p-1 rounded border border-[#14141A] bg-[#FAF9F5]">
                          <Lock className="w-3.5 h-3.5 text-[#14141A]" />
                        </span>
                      ) : (
                        <span title="Public repository" className="p-1 rounded border border-[#14141A] bg-[#FAF9F5]">
                          <Globe className="w-3.5 h-3.5 text-[#55555F]" />
                        </span>
                      )}
                      <Link
                        href={`/repos/${repo.id}`}
                        className="font-bold text-base text-[#14141A] hover:underline truncate"
                      >
                        {repo.full_name}
                      </Link>
                    </div>

                    <span className="inline-flex items-center gap-1 font-mono text-[10px] font-bold px-2 py-0.5 rounded-full border border-[#14141A] bg-[#F5F4EE] text-[#14141A] flex-shrink-0">
                      <GitBranch className="w-3 h-3" />
                      <span>{repo.default_branch}</span>
                    </span>
                  </div>

                  {/* Scan Metrics */}
                  <div className="border-t border-b border-[#E2E0D6] py-3 flex flex-col gap-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-mono text-[#55555F]">
                        Status:
                      </span>
                      <span className="font-mono font-bold text-[#14141A]">
                        {latest ? latest.status.toUpperCase() : 'NOT SCANNED'}
                      </span>
                    </div>

                    {latest ? (
                      <div className="flex items-center gap-1.5 flex-wrap pt-1">
                        <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded border border-[#14141A] bg-[#FF6B3D] text-white">
                          CRIT: {latest.critical_count || 0}
                        </span>
                        <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded border border-[#14141A] bg-[#FFC93C] text-[#14141A]">
                          HIGH: {latest.high_count || 0}
                        </span>
                        <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded border border-[#14141A] bg-[#F5F4EE] text-[#14141A]">
                          MED: {latest.medium_count || 0}
                        </span>
                        <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded border border-[#14141A] bg-[#F5F4EE] text-[#14141A]">
                          LOW: {latest.low_count || 0}
                        </span>
                      </div>
                    ) : (
                      <span className="font-mono text-[11px] text-[#888891]">
                        No scans recorded yet. Trigger a scan below.
                      </span>
                    )}

                    <div className="flex items-center justify-between text-[11px] font-mono text-[#888891] pt-1">
                      <span>Last checked: {formatTimeAgo(latest?.timestamp || repo.last_scanned_at)}</span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center justify-between gap-3 pt-1">
                    <button
                      onClick={() => handleQuickScan(repo)}
                      disabled={isTriggering}
                      className="inline-flex items-center gap-1.5 px-4 py-2 border-2 border-[#14141A] rounded-full bg-[#FAF9F5] text-[#14141A] font-mono text-xs font-bold hover:bg-[#F5F4EE] active:translate-x-0.5 active:translate-y-0.5 shadow-[2px_2px_0_#14141A] active:shadow-none transition-all cursor-pointer disabled:opacity-50"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${isTriggering ? 'animate-spin' : ''}`} />
                      <span>{isTriggering ? 'Starting...' : 'Scan now'}</span>
                    </button>

                    <Link
                      href={`/repos/${repo.id}`}
                      className="inline-flex items-center gap-1.5 px-4 py-2 border-2 border-[#14141A] rounded-full bg-[#14141A] text-white font-mono text-xs font-bold hover:bg-[#2B2B36] active:translate-x-0.5 active:translate-y-0.5 shadow-[2px_2px_0_#D6F25B] active:shadow-none transition-all cursor-pointer"
                    >
                      <span>Overview</span>
                      <ArrowRight className="w-3.5 h-3.5 text-[#D6F25B]" />
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={
      <div className="max-w-[1160px] mx-auto w-full py-4 px-4 sm:px-6 flex flex-col gap-6">
        <SkeletonCard />
      </div>
    }>
      <DashboardContent />
    </Suspense>
  );
}
