// Next.js API Client configuration

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface ScanMetadata {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  error_message: string | null;
  total_issues: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  filename: string;
  timestamp: string;
  file_size: number;
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

// Global fetch helper
export async function fetchApi(endpoint: string, options: RequestInit = {}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('admin_token') : null;
  
  options.headers = {
    ...options.headers,
  } as Record<string, string>;

  if (token) {
    (options.headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, options);

  if (response.status === 401 && endpoint !== '/admin/api/login') {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('admin_token');
      localStorage.removeItem('admin_username');
      window.dispatchEvent(new Event('auth-change'));
    }
  }

  return response;
}
