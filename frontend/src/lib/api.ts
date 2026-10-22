// Next.js API Client configuration
// In browser, use relative paths to leverage Next.js rewrite proxy (/api/*).
// In SSR or custom envs, fall back to BACKEND_API_URL or localhost.
export const API_BASE = typeof window !== 'undefined'
  ? '' 
  : (process.env.BACKEND_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000');

export interface User {
  id: number;
  username: string;
  github_id?: number | null;
  github_login?: string | null;
  avatar_url?: string | null;
  role: string;
}

export interface Installation {
  id: string;
  github_installation_id: number;
  account_login: string;
  account_type: string;
  account_avatar_url?: string | null;
  suspended_at?: string | null;
  created_at: string;
}

export interface Repository {
  id: string;
  installation_id: string;
  github_repo_id: number;
  full_name: string;
  default_branch: string;
  is_private: boolean;
  scan_enabled: boolean;
  settings?: Record<string, any>;
  last_scanned_at?: string | null;
  created_at: string;
  latest_scan?: ScanMetadata | null;
}

export interface GitHubUserRepo {
  id: number;
  name: string;
  full_name: string;
  private: boolean;
  html_url: string;
  default_branch: string;
  description?: string | null;
  updated_at?: string;
  connected?: boolean;
  connected_repo_id?: string | null;
}

export interface ScanMetadata {
  id: string;
  repo_id?: string | null;
  owner_user_id?: number | null;
  trigger?: 'manual' | 'push' | 'pr' | 'schedule';
  pr_number?: number | null;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress?: string;
  error_message: string | null;
  total_issues: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  filename: string;
  timestamp: string;
  file_size: number;
  source_type?: 'paste' | 'zip' | 'github_public' | 'github_app';
  source_url?: string | null;
  branch?: string | null;
  commit_sha?: string | null;
  duration_ms?: number;
  files_scanned?: number;
  files_skipped?: number;
  new_findings_count?: number;
  fixed_findings_count?: number;
  existing_findings_count?: number;
  verdict?: string;
  check_run_id?: number | null;
}

export interface Issue {
  id: number;
  scan_id: string;
  scanner: string;
  rule_id: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  message: string;
  filepath: string;
  line_number: number;
  col_number: number;
  code_snippet: string;
  fingerprint?: string;
  state?: string;
  fix_title: string;
  fix_description: string;
  fix_before: string;
  fix_after: string;
  doc_url: string | null;
}

export interface AuditLog {
  id: number;
  timestamp: string;
  user_id: number;
  username: string;
  action: string;
  details: string | null;
  ip_address: string | null;
}

export interface DbStats {
  total_scans: number;
  status_counts: {
    completed: number;
    pending: number;
    running: number;
    failed: number;
  };
  issue_sums: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    total: number;
  };
  db_size_kb: number;
}

export interface PRSummaryFacts {
  version: number;
  pr: {
    number: number;
    head_sha: string;
    base_sha: string;
    title: string;
    author: string;
    files_changed: number;
    additions: number;
    deletions: number;
  };
  categories_touched: string[];
  findings: {
    new: Array<{
      finding_id?: string | null;
      fingerprint: string;
      severity: 'critical' | 'high' | 'medium' | 'low';
      rule_id: string;
      message: string;
      file: string;
      line: number;
      has_verified_fix?: boolean | null;
    }>;
    fixed: Array<{
      finding_id?: string | null;
      fingerprint: string;
      severity: string;
      rule_id: string;
      message: string;
      file: string;
      line: number;
    }>;
    existing_touched: Array<any>;
    hidden_existing_count: number;
  };
  dependency_changes: Array<{
    ecosystem: string;
    name: string;
    change_type: string;
    version?: string | null;
    previous_version?: string | null;
    manifest_file: string;
  }>;
  delta_since_previous_push: {
    new_count: number;
    fixed_count: number;
    delta_new: number;
    delta_fixed: number;
    previous_head_sha?: string | null;
  };
  verdict: 'block' | 'attention' | 'safe';
  reasons: string[];
  actions: Array<{
    priority: number;
    category: string;
    title: string;
    description: string;
    finding_id?: string | null;
    fingerprint?: string | null;
    file?: string | null;
    line?: number | null;
  }>;
  omitted_actions_count: number;
}

export interface PRSummaryRecord {
  id: string;
  repo_id: string;
  pr_number: number;
  scan_id: string;
  head_sha: string;
  facts: PRSummaryFacts;
  narrative?: string | null;
  narrative_source: string;
  model?: string | null;
  summary_version: number;
  created_at: string;
}

// Global fetch helper
export async function fetchApi(endpoint: string, options: RequestInit = {}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('admin_token') : null;
  
  options.credentials = 'include';
  options.headers = {
    ...options.headers,
  } as Record<string, string>;

  if (token) {
    (options.headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }

  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
  const response = await fetch(url, options);

  if (response.status === 401 && endpoint !== '/admin/api/login') {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('admin_token');
      localStorage.removeItem('admin_username');
      window.dispatchEvent(new Event('auth-change'));
    }
  }

  return response;
}

export interface FixAttempt {
  id: string;
  finding_id: string;
  repo_id: string;
  status: 'generated' | 'verified' | 'rejected' | 'pr_opened' | 'merged' | 'closed';
  provider?: string | null;
  model?: string | null;
  target_file: string;
  target_function?: string | null;
  start_line?: number | null;
  end_line?: number | null;
  diff?: string | null;
  patch_code?: string | null;
  explanation?: string | null;
  verification_json?: {
    is_verified?: boolean;
    scanners_run?: string[];
    syntax_valid?: boolean;
    original_fingerprint_resolved?: boolean;
    new_findings_count?: number;
  } | null;
  rejection_reason?: string | null;
  tokens_in?: number;
  tokens_out?: number;
  cost_usd?: number;
  pr_number?: number | null;
  pr_url?: string | null;
  branch_name?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface AutofixQuota {
  autofix_enabled: boolean;
  daily_quota: number;
  used_today: number;
  remaining: number;
}

export async function generateFindingFix(repoId: string, findingId: string, fileContent?: string): Promise<{ fix_attempt: FixAttempt }> {
  const res = await fetchApi(`/api/repos/${repoId}/findings/${findingId}/fix`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fileContent ? { file_content: fileContent } : {})
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to generate fix.' }));
    throw new Error(err.detail || `Auto-fix request failed (${res.status})`);
  }
  return res.json();
}

export async function getLatestFindingFix(repoId: string, findingId: string): Promise<{ fix_attempt: FixAttempt | null }> {
  const res = await fetchApi(`/api/repos/${repoId}/findings/${findingId}/fix`);
  if (!res.ok) {
    return { fix_attempt: null };
  }
  return res.json();
}

export async function createFindingFixPR(repoId: string, findingId: string): Promise<{ pr_number: number; pr_url: string; branch_name: string }> {
  const res = await fetchApi(`/api/repos/${repoId}/findings/${findingId}/fix/pr`, {
    method: 'POST'
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to open fix PR.' }));
    throw new Error(err.detail || `PR creation failed (${res.status})`);
  }
  return res.json();
}

export async function getAutofixQuota(repoId: string): Promise<AutofixQuota> {
  const res = await fetchApi(`/api/repos/${repoId}/autofix/quota`);
  if (!res.ok) {
    return { autofix_enabled: false, daily_quota: 20, used_today: 0, remaining: 20 };
  }
  return res.json();
}

export async function triggerHistoryScan(repoId: string): Promise<{ status: string; scan_id: string; repo_id: string }> {
  const res = await fetchApi(`/api/repos/${repoId}/scan/history`, {
    method: 'POST'
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to trigger history scan.' }));
    throw new Error(err.detail || `History scan request failed (${res.status})`);
  }
  return res.json();
}

