'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Shield, Trash2, Scroll, Loader2, Database, ShieldAlert, CheckCircle, XCircle } from 'lucide-react';
import { useToast } from '@/components/ToastProvider';
import { fetchApi, DbStats, AuditLog, ScanMetadata } from '@/lib/api';

export default function AdminDashboardPage() {
  const router = useRouter();
  const { showToast } = useToast();
  
  const [stats, setStats] = useState<DbStats | null>(null);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [wipeLoading, setWipeLoading] = useState<boolean>(false);

  const loadStats = async () => {
    try {
      const response = await fetchApi('/admin/api/stats');
      if (!response.ok) {
        if (response.status === 401) {
          router.push('/admin/login');
          return;
        }
        throw new Error("Failed to load admin stats from server.");
      }
      const data = await response.json();
      setStats(data.stats);
      setLogs(data.audit_logs);
    } catch (error) {
      console.error(error);
      showToast("Failed to load control room data.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('admin_token')) {
      router.push('/admin/login');
      return;
    }
    loadStats();
  }, []);

  const handleWipe = async () => {
    if (!confirm("CRITICAL WARNING: This will permanently wipe all scan records, issue findings, and audit logs. This cannot be undone! Are you absolutely sure?")) {
      return;
    }
    
    setWipeLoading(true);
    try {
      const response = await fetchApi("/admin/api/wipe", {
        method: "POST"
      });
      
      if (!response.ok) throw new Error("Wipe database authorization denied.");
      showToast("System database wiped successfully.", "success");
      loadStats(); // reload metrics
    } catch (error: any) {
      console.error(error);
      showToast(error.message || "Failed to wipe database records.", "error");
    } finally {
      setWipeLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 flex-grow w-full">
        <Loader2 className="w-10 h-10 text-primary animate-spin" />
        <p className="text-xs text-slate-500 font-bold mt-2">Connecting to Admin Control Room...</p>
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="space-y-8 animate-slide-up w-full text-slate-800 flex-grow">
      {/* Title Row */}
      <div className="flex flex-col sm:flex-row items-center justify-between border-b-4 border-slate-900 pb-4 gap-4">
        <div className="text-center sm:text-left">
          <h2 className="text-xl font-black uppercase text-slate-800 flex items-center justify-center sm:justify-start gap-2">
            <Shield className="w-5 h-5 text-primary" />
            Vanguard Admin Headquarters
          </h2>
          <p className="text-xs text-slate-400 font-bold mt-1">Manage static security runner queues, database records, and audit actions.</p>
        </div>
        
        <button 
          onClick={handleWipe}
          disabled={wipeLoading}
          className="cartoon-btn cartoon-btn-sm bg-red-500 hover:bg-red-600 text-white px-4 py-2 text-xs gap-1.5 flex items-center cursor-pointer"
        >
          {wipeLoading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Purging...
            </>
          ) : (
            <>
              <Trash2 className="w-4 h-4" />
              Wipe System Records
            </>
          )}
        </button>
      </div>

      {/* Database Metrics Hud */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="cartoon-card p-6 text-center space-y-1.5 bg-white">
          <div className="text-3xl font-black text-slate-800">{stats.total_scans}</div>
          <div className="text-[9px] text-slate-450 font-black uppercase tracking-wider">Total Scans Triggered</div>
        </div>
        
        <div className="cartoon-card p-6 text-center space-y-1.5 bg-white border-l-8 border-l-[#10b981]">
          <div className="text-3xl font-black text-[#10b981]">{stats.status_counts.completed}</div>
          <div className="text-[9px] text-slate-455 font-black uppercase tracking-wider">Completed Runs</div>
        </div>

        <div className="cartoon-card p-6 text-center space-y-1.5 bg-white border-l-8 border-l-error">
          <div className="text-3xl font-black text-error">{stats.status_counts.failed}</div>
          <div className="text-[9px] text-slate-455 font-black uppercase tracking-wider">Failed Runs</div>
        </div>

        <div className="cartoon-card p-6 text-center space-y-1.5 bg-white border-l-8 border-l-primary">
          <div className="text-3xl font-black text-primary">{stats.db_size_kb} KB</div>
          <div className="text-[9px] text-slate-455 font-black uppercase tracking-wider">SQLite Disk Size</div>
        </div>
      </div>

      {/* Threat Registry Totals */}
      <div className="cartoon-card p-6 space-y-4 bg-white">
        <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest">Historical Threat Intel Sums</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="bg-slate-50 p-4 rounded-xl border-2 border-slate-900 text-center">
            <p className="text-xl font-black text-slate-800">{stats.issue_sums.total}</p>
            <p className="text-[8px] text-slate-400 font-bold uppercase mt-1">Total Flaws Found</p>
          </div>
          <div className="bg-red-50 p-4 rounded-xl border-2 border-red-200 text-center">
            <p className="text-xl font-black text-error">{stats.issue_sums.critical}</p>
            <p className="text-[8px] text-slate-400 font-bold uppercase mt-1">Critical Bosses</p>
          </div>
          <div className="bg-orange-50 p-4 rounded-xl border-2 border-orange-200 text-center">
            <p className="text-xl font-black text-orange-500">{stats.issue_sums.high}</p>
            <p className="text-[8px] text-slate-400 font-bold uppercase mt-1">High Threats</p>
          </div>
          <div className="bg-yellow-50 p-4 rounded-xl border-2 border-yellow-200 text-center">
            <p className="text-xl font-black text-yellow-600">{stats.issue_sums.medium}</p>
            <p className="text-[8px] text-slate-400 font-bold uppercase mt-1">Medium Threats</p>
          </div>
          <div className="bg-sky-50 p-4 rounded-xl border-2 border-sky-200 text-center">
            <p className="text-xl font-black text-info">{stats.issue_sums.low}</p>
            <p className="text-[8px] text-slate-400 font-bold uppercase mt-1">Low Warnings</p>
          </div>
        </div>
      </div>

      {/* Audit Logs Section */}
      <div className="space-y-4">
        <h3 className="text-xs font-black text-slate-800 uppercase tracking-widest flex items-center gap-1.5">
          <Scroll className="w-4.5 h-4.5 text-primary" />
          Security Audit Logs
        </h3>
        
        <div className="cartoon-card">
          {/* Window header */}
          <div className="window-header bg-slate-900 text-white flex items-center justify-between px-4 py-2 border-b-4 border-slate-900 select-none">
            <span className="text-[10px] font-black uppercase tracking-widest font-mono text-slate-300">system_audit_logs.txt</span>
            <div className="window-dots flex gap-1">
              <span className="w-2.5 h-2.5 rounded-full bg-slate-700"></span>
            </div>
          </div>

          <div className="overflow-x-auto bg-white p-4">
            <table className="table w-full text-slate-800 text-xs font-semibold">
              <thead>
                <tr className="border-b-4 border-slate-900 text-[10px] font-black text-slate-400 uppercase tracking-wider text-left">
                  <th className="py-2.5 px-3">Timestamp</th>
                  <th className="py-2.5 px-3">Operator</th>
                  <th className="py-2.5 px-3">Action</th>
                  <th className="py-2.5 px-3">Details</th>
                  <th className="py-2.5 px-3 text-right">IP Address</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => {
                  const time = log.timestamp.substring(0, 19).replace('T', ' ');
                  return (
                    <tr key={log.id} className="hover:bg-slate-50/50 border-b border-slate-100">
                      <td className="font-mono text-[10px] text-slate-500 py-3 px-3">{time}</td>
                      <td className="py-3 px-3">
                        <span className="cartoon-badge bg-slate-100 border-slate-350 text-slate-700 text-[8px]">
                          {log.username}
                        </span>
                      </td>
                      <td className="font-bold text-slate-800 py-3 px-3">{log.action}</td>
                      <td className="text-slate-500 max-w-sm truncate py-3 px-3" title={log.details || ''}>
                        {log.details || '—'}
                      </td>
                      <td className="font-mono text-[10px] text-slate-400 text-right py-3 px-3">
                        {log.ip_address || 'unknown'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
