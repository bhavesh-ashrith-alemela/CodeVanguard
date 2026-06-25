'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { History, Archive, Trash2, Shield } from 'lucide-react';
import { useToast } from '@/components/ToastProvider';
import { fetchApi, ScanMetadata } from '@/lib/api';

export default function HistoryPage() {
  const { showToast } = useToast();
  
  const [history, setHistory] = useState<ScanMetadata[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isAdmin, setIsAdmin] = useState<boolean>(false);

  const loadHistory = async () => {
    try {
      const response = await fetchApi('/api/history/json');
      if (!response.ok) throw new Error("Failed to read history records.");
      const data = await response.json();
      setHistory(data.history);
    } catch (error) {
      console.error(error);
      showToast("Could not load scan history from database.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
    if (typeof window !== 'undefined') {
      setIsAdmin(!!localStorage.getItem('admin_username'));
    }
  }, []);

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to purge this scan history row? This action is irreversible.")) return;

    try {
      const response = await fetchApi(`/api/scans/${id}`, {
        method: "DELETE"
      });

      if (!response.ok) throw new Error("Deletion request denied.");
      showToast("Scan purged successfully.", "success");
      loadHistory(); // refresh list
    } catch (error) {
      console.error(error);
      showToast("Failed to delete scan from database.", "error");
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6 animate-slide-up w-full text-slate-800">
      
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-black uppercase text-slate-800 tracking-wider flex items-center gap-2">
          <History className="w-5 h-5 text-primary" />
          Terminal Audit Records
        </h2>
        <span className="text-xs font-mono font-bold text-slate-500 uppercase">
          {loading ? 'LOADING...' : `${history.length} RUNS LOADED`}
        </span>
      </div>

      <div className="cartoon-card">
        {/* Window Decor header */}
        <div className="window-header bg-slate-900 text-white flex items-center justify-between px-4 py-2 border-b-4 border-slate-900 select-none">
          <span className="text-[10px] font-black uppercase tracking-widest font-mono text-slate-300">security_scan_history.log</span>
          <div className="window-dots flex gap-1.5">
            <span className="w-3 h-3 rounded-full bg-slate-700"></span>
            <span className="w-3 h-3 rounded-full bg-slate-700"></span>
          </div>
        </div>

        <div className="overflow-x-auto bg-white p-4">
          {loading ? (
            <div className="text-center py-12">
              <span className="loading loading-ring loading-md text-primary"></span>
              <p className="text-[10px] text-slate-400 font-bold mt-1">Retrieving database log rows...</p>
            </div>
          ) : history.length === 0 ? (
            <div className="text-center py-12">
              <div className="max-w-sm mx-auto space-y-2">
                <span className="p-2.5 bg-slate-100 rounded-lg text-slate-400 border border-slate-200 inline-block">
                  <Archive className="w-6 h-6" />
                </span>
                <p className="font-extrabold text-slate-700">Empty Logs database</p>
                <p className="text-[10px] text-slate-400">No scan history was found in the SQLite backend. Initialize a scan to record results.</p>
              </div>
            </div>
          ) : (
            <table className="table w-full text-slate-800 text-xs font-semibold">
              <thead>
                <tr className="border-b-4 border-slate-900 text-[10px] font-black text-slate-400 uppercase tracking-wider text-left">
                  <th className="py-3 px-4">Scan Target / ID</th>
                  <th className="py-3 px-4">Timestamp</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-center">Score details</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {history.map((scan) => {
                  const date = scan.timestamp.substring(0, 19).replace('T', ' ');
                  const sizeKB = (scan.file_size / 1024).toFixed(1);
                  
                  // Status badge
                  let statusBadge = "";
                  if (scan.status === "completed") {
                    statusBadge = `<span class="cartoon-badge bg-green-50 text-green-700 border-green-400 text-[8px] font-black">completed</span>`;
                  } else if (scan.status === "failed") {
                    statusBadge = `<span class="cartoon-badge bg-red-50 text-red-700 border-red-400 text-[8px] font-black">failed</span>`;
                  } else {
                    statusBadge = `<span class="cartoon-badge bg-primary/10 text-primary border-primary text-[8px] font-black animate-pulse">${scan.status}</span>`;
                  }
                  
                  return (
                    <tr key={scan.id} className="hover:bg-slate-50/50 border-b border-slate-100">
                      <td className="font-bold py-3.5 px-4">
                        <p className="text-slate-800 font-extrabold max-w-[200px] sm:max-w-xs truncate">{scan.filename}</p>
                        <p className="text-[9px] font-mono text-slate-400 font-bold">{scan.id} ({sizeKB} KB)</p>
                      </td>
                      <td className="font-mono text-[10px] text-slate-550 py-3.5 px-4">{date}</td>
                      <td className="py-3.5 px-4">
                        <div dangerouslySetInnerHTML={{ __html: statusBadge }} />
                      </td>
                      <td className="text-center py-3.5 px-4">
                        {scan.status === 'completed' ? (
                          <div className="flex items-center justify-center gap-1.5 font-mono text-[10px] font-bold">
                            <span className="text-error" title="Critical">{scan.critical_count}</span>
                            <span className="text-slate-300">/</span>
                            <span className="text-orange-500" title="High">{scan.high_count}</span>
                            <span className="text-slate-300">/</span>
                            <span className="text-yellow-600" title="Medium">{scan.medium_count}</span>
                            <span className="text-slate-300">/</span>
                            <span className="text-info" title="Low">{scan.low_count}</span>
                          </div>
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Link href={`/results?id=${scan.id}`} className="cartoon-btn btn-xs px-2.5 py-1 rounded-md text-[9px]">
                            Terminal
                          </Link>
                          {isAdmin && (
                            <button 
                              onClick={() => handleDelete(scan.id)}
                              className="cartoon-btn btn-xs bg-red-100 hover:bg-red-500 hover:text-white text-red-500 border-red-500 px-2.5 py-1 rounded-md text-[9px] cursor-pointer"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
      
    </div>
  );
}
