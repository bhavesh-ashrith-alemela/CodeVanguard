'use client';

import React, { useState, useEffect, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { 
  Shield, AlertTriangle, FileText, CheckCircle, XCircle, Search, 
  ExternalLink, Trophy, HelpCircle, AlertCircle, Info, Loader2 
} from 'lucide-react';
import { useToast } from '@/components/ToastProvider';
import { fetchApi, API_BASE, ScanMetadata, Issue } from '@/lib/api';

function ResultsClient() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { showToast } = useToast();
  
  const scanId = searchParams.get('id');

  const [scan, setScan] = useState<ScanMetadata | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  
  // Filter States
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [scannerFilter, setScannerFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  
  // Polling Timer States
  const [elapsedTime, setElapsedTime] = useState<number>(0);
  const [scanStartTime] = useState<number>(Date.now());

  useEffect(() => {
    if (!scanId) {
      setLoading(false);
      setErrorMsg("No scan ID was provided.");
      return;
    }

    let intervalId: NodeJS.Timeout;
    
    // Timer increment
    const timerId = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - scanStartTime) / 1000));
    }, 1000);

    const checkStatus = async () => {
      try {
        const response = await fetchApi(`/api/scans/${scanId}/status`);
        if (!response.ok) {
          throw new Error("Unable to retrieve scan status.");
        }
        const data = await response.json();
        
        if (data.status === 'completed') {
          clearInterval(intervalId);
          clearInterval(timerId);
          fetchFindings();
        } else if (data.status === 'failed') {
          clearInterval(intervalId);
          clearInterval(timerId);
          setScan(data);
          setErrorMsg(data.error_message || "Static analysis engine failed.");
          setLoading(false);
        } else {
          setScan(data);
        }
      } catch (error: any) {
        console.error(error);
        showToast("Connection issue. Re-establishing terminal hook...", "info");
      }
    };

    const fetchFindings = async () => {
      try {
        const response = await fetchApi(`/api/scans/${scanId}/issues`);
        if (!response.ok) throw new Error("Failed to load issues registry.");
        const data = await response.json();
        
        setScan(data.scan);
        setIssues(data.issues);
        setLoading(false);
      } catch (error: any) {
        console.error(error);
        showToast(error.message || "Failed to fetch scan results.", "error");
        setLoading(false);
      }
    };

    checkStatus();
    intervalId = setInterval(checkStatus, 2000);

    return () => {
      clearInterval(intervalId);
      clearInterval(timerId);
    };
  }, [scanId]);

  if (!scanId) {
    return (
      <div className="cartoon-card bg-white p-8 text-center max-w-md mx-auto space-y-4">
        <span className="p-3 bg-red-50 text-error rounded-full inline-block border-2 border-slate-900 shadow-[2px_2px_0px_#000]">
          <AlertCircle className="w-8 h-8" />
        </span>
        <h3 className="text-lg font-black text-slate-800 uppercase">Invalid Request</h3>
        <p className="text-xs text-slate-500 font-bold">No scan identification code was supplied. Please return home and scan a codebase.</p>
        <button onClick={() => router.push('/')} className="cartoon-btn cartoon-btn-sm px-4 py-2 text-xs mx-auto">
          Go Home
        </button>
      </div>
    );
  }

  if (loading && (!scan || (scan.status !== 'completed' && scan.status !== 'failed'))) {
    return (
      <div className="cartoon-card bg-white p-8 md:p-12 text-center relative overflow-hidden animate-slide-up w-full max-w-xl mx-auto">
        <div className="absolute -top-12 -left-12 w-32 h-32 bg-primary/5 rounded-full blur-3xl pointer-events-none"></div>
        <div className="absolute -bottom-12 -right-12 w-32 h-32 bg-primary/5 rounded-full blur-3xl pointer-events-none"></div>
      
        <div className="max-w-md mx-auto space-y-6">
          <div className="relative flex items-center justify-center w-20 h-20 mx-auto">
            <span className="absolute w-16 h-16 rounded-full border-4 border-primary/20 animate-ping"></span>
            <Loader2 className="w-10 h-10 text-primary animate-spin scale-150 relative z-10" />
          </div>
      
          <div className="space-y-1">
            <h3 className="text-xl font-extrabold text-slate-800 tracking-tight">ACTIVE SCANNING RUN</h3>
            <p className="text-xs text-slate-400 italic h-6">Analyzing file imports and dependency trees...</p>
          </div>
      
          <div className="space-y-2">
            <div className="h-4 bg-white border-2 border-slate-900 rounded-lg overflow-hidden relative">
              <div className="h-full bg-primary border-r-2 border-slate-900 animate-pulse" style={{ width: '45%' }}></div>
            </div>
            <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
              <span>QUEST STATUS: <span className="text-primary font-bold uppercase">{scan?.status || 'PENDING'}</span></span>
              <span>TIME ELAPSED: {elapsedTime}s</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (errorMsg) {
    return (
      <div className="cartoon-card bg-white p-8 text-center space-y-6 max-w-xl mx-auto animate-slide-up w-full">
        <div className="space-y-4">
          <span className="p-3.5 bg-red-55 text-error inline-block border-2 border-slate-900 shadow-[2px_2px_0px_#000]">
            <AlertTriangle className="w-10 h-10" />
          </span>
          <h3 className="text-lg font-extrabold text-slate-800 uppercase tracking-tight">Scan Quest Interrupted</h3>
          <p className="text-xs text-slate-500 font-bold">
            An unexpected error occurred while executing the static analysis engines. Please inspect the log outputs below.
          </p>
        </div>
        
        <div className="bg-slate-50 p-4 rounded-lg text-left border border-slate-900 font-mono text-[10px] overflow-x-auto text-error leading-relaxed">
          <strong>Traceback details:</strong>
          <pre className="mt-2 whitespace-pre-wrap">{errorMsg}</pre>
        </div>
        
        <div className="pt-2">
          <button onClick={() => router.push('/')} className="cartoon-btn cartoon-btn-sm px-4 py-2 text-xs mx-auto">
            Return Home
          </button>
        </div>
      </div>
    );
  }

  if (!scan) return null;

  // Grade calculation
  const total_crit = scan.critical_count;
  const total_high = scan.high_count;
  const total_med = scan.medium_count;
  
  let grade = "S";
  let hp = 100;
  let color = "text-[#10b981] border-[#10b981] bg-green-50 shadow-[3px_3px_0px_#000]";
  let barColor = "bg-[#10b981]";
  let title = "FLAWLESS RUN!";
  let desc = "Zero security defects found. Your codebase is officially impenetrable.";
  let xp = "+1200 XP (PERFECT SCORE!)";

  if (total_crit > 0 || total_high > 2) {
    grade = "F";
    hp = 20;
    color = "text-error border-error bg-red-50 shadow-[3px_3px_0px_#000]";
    barColor = "bg-error";
    title = "SHIELD BROKEN";
    desc = "Vulnerabilities detected. Defeat the bosses below to repair the shield.";
    xp = "+50 XP (Stage Initiated)";
  } else if (total_high > 0 || total_med > 4) {
    grade = "C";
    hp = 55;
    color = "text-orange-500 border-orange-500 bg-orange-50 shadow-[3px_3px_0px_#000]";
    barColor = "bg-orange-500";
    title = "SHIELD WARNING";
    desc = "Significant security threats found. Review the remediation blueprints.";
    xp = "+200 XP (Stage Cleared)";
  } else if (total_med > 0) {
    grade = "B";
    hp = 80;
    color = "text-yellow-600 border-yellow-500 bg-yellow-50 shadow-[3px_3px_0px_#000]";
    barColor = "bg-yellow-500";
    title = "SHIELD STABLE";
    desc = "Minor warnings found. Fix them to upgrade your shield to maximum capacity.";
    xp = "+450 XP (Advanced Defender)";
  } else if (scan.low_count > 0) {
    grade = "A";
    hp = 95;
    color = "text-info border-info bg-sky-50 shadow-[3px_3px_0px_#000]";
    barColor = "bg-info";
    title = "SHIELD SECURE";
    desc = "Excellent code structure. Clean imports and safe syntax usage throughout.";
    xp = "+750 XP (Champion Builder)";
  }

  // Filter Logic
  const filteredIssues = issues.filter(issue => {
    const matchSeverity = severityFilter === 'all' || issue.severity === severityFilter;
    const matchScanner = scannerFilter === 'all' || issue.scanner === scannerFilter;
    const searchString = `${issue.filepath} ${issue.message} ${issue.rule_id} ${issue.fix_title}`.toLowerCase();
    const matchSearch = !searchQuery || searchString.includes(searchQuery.toLowerCase());
    return matchSeverity && matchScanner && matchSearch;
  });

  return (
    <div className="space-y-8 animate-slide-up w-full text-slate-800">
      
      {/* Top Export Panel */}
      <div className="cartoon-card">
        <div className="window-header bg-slate-900 text-white flex items-center justify-between px-4 py-2 border-b-4 border-slate-900 select-none">
          <span className="text-[10px] font-black uppercase tracking-widest font-mono text-slate-300">report_exporter_subroutine.sh</span>
          <div className="window-dots flex gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-700"></span>
            <span className="w-2.5 h-2.5 rounded-full bg-slate-700"></span>
          </div>
        </div>
        <div className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="text-xs font-black text-slate-500 uppercase tracking-widest">Compliance Logs:</span>
            <a href={`${API_BASE}/scans/${scanId}/export/pdf`} download className="cartoon-btn cartoon-btn-sm bg-red-500 hover:bg-red-600 text-white px-3 py-1 flex items-center gap-1 text-[10px] font-black">
              <FileText className="w-3.5 h-3.5" /> PDF
            </a>
            <a href={`${API_BASE}/scans/${scanId}/export/html`} download className="cartoon-btn cartoon-btn-sm bg-slate-900 hover:bg-slate-800 text-white px-3 py-1 flex items-center gap-1 text-[10px] font-black">
              <FileText className="w-3.5 h-3.5" /> HTML
            </a>
            <a href={`${API_BASE}/scans/${scanId}/export/json`} download className="cartoon-btn cartoon-btn-sm bg-white hover:bg-slate-100 text-slate-800 px-3 py-1 flex items-center gap-1 text-[10px] font-black">
              <FileText className="w-3.5 h-3.5" /> JSON
            </a>
            <a href={`${API_BASE}/scans/${scanId}/export/csv`} download className="cartoon-btn cartoon-btn-sm bg-white hover:bg-slate-100 text-slate-800 px-3 py-1 flex items-center gap-1 text-[10px] font-black">
              <FileText className="w-3.5 h-3.5" /> CSV
            </a>
          </div>
          
          <div className="text-[10px] text-slate-400 font-mono font-bold">
            COMPLETED RUN: {scan.timestamp.substring(0, 19).replace('T', ' ')}
          </div>
        </div>
      </div>

      {/* HUD Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Shield Integrity */}
        <div className="cartoon-card p-6 space-y-4 lg:col-span-2 flex flex-col justify-between bg-white">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-black text-slate-400 uppercase tracking-widest">Shield Integrity Monitor</span>
              <span className="text-xs font-black text-primary font-mono uppercase tracking-wider">{title}</span>
            </div>
            
            <div className="space-y-2">
              <div className="flex justify-between items-center text-[10px] font-mono font-black text-slate-600 uppercase">
                <span>Shield capacity: {hp} HP / 100 HP</span>
                <span>Quest XP: <span className="text-primary font-black">{xp}</span></span>
              </div>
              <div className="cartoon-bar">
                <div className={`cartoon-bar-fill ${barColor}`} style={{ width: `${hp}%` }}></div>
              </div>
            </div>
          </div>

          <p className="text-xs text-slate-500 font-bold leading-relaxed pt-2 border-t border-slate-100 mt-2">
            <strong>Vanguard evaluation:</strong> {desc}
          </p>
        </div>

        {/* Grade */}
        <div className="cartoon-card p-6 flex flex-row items-center gap-6 justify-center bg-white">
          <div className={`w-20 h-20 rounded-full border-4 border-slate-900 flex items-center justify-center font-black text-3xl ${color}`}>
            {grade}
          </div>
          <div className="space-y-1 text-left">
            <div className="text-xs font-black text-slate-400 uppercase tracking-widest">Rank Score</div>
            <div className="text-sm font-black text-slate-800 uppercase tracking-tight">
              {grade === 'S' || grade === 'A' ? 'Secure Cleared' : 'Stage Insecure'}
            </div>
            <div className="text-[9px] text-slate-400 font-bold uppercase">Evaluated by Boss Threats</div>
          </div>
        </div>

      </div>

      {/* Stats Summary Tally */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="cartoon-card p-4 text-center space-y-1 bg-white">
          <div className="text-2xl font-black text-slate-800">{scan.total_issues}</div>
          <div className="text-[9px] text-slate-400 font-black uppercase tracking-wider">Total Threats</div>
        </div>
        <div className="cartoon-card p-4 text-center space-y-1 border-l-8 border-l-error bg-white">
          <div className="text-2xl font-black text-error">{scan.critical_count}</div>
          <div className="text-[9px] text-slate-400 font-black uppercase tracking-wider">Critical</div>
        </div>
        <div className="cartoon-card p-4 text-center space-y-1 border-l-8 border-l-orange-500 bg-white">
          <div className="text-2xl font-black text-orange-500">{scan.high_count}</div>
          <div className="text-[9px] text-slate-400 font-black uppercase tracking-wider">High</div>
        </div>
        <div className="cartoon-card p-4 text-center space-y-1 border-l-8 border-l-yellow-500 bg-white">
          <div className="text-2xl font-black text-yellow-600">{scan.medium_count}</div>
          <div className="text-[9px] text-slate-400 font-black uppercase tracking-wider">Medium</div>
        </div>
        <div className="cartoon-card p-4 text-center space-y-1 border-l-8 border-l-info bg-white">
          <div className="text-2xl font-black text-info">{scan.low_count}</div>
          <div className="text-[9px] text-slate-400 font-black uppercase tracking-wider">Low</div>
        </div>
      </div>

      {/* Filters & Search */}
      <div className="cartoon-card p-4 space-y-4 bg-white">
        <div className="flex flex-col lg:flex-row gap-4 items-stretch lg:items-center justify-between">
          
          {/* Severity filter buttons */}
          <div className="flex flex-wrap gap-1 bg-slate-100 p-1 rounded-lg border-2 border-slate-900 w-fit text-[10px] font-black uppercase shadow-[2px_2px_0px_#0f172a]">
            {(['all', 'critical', 'high', 'medium', 'low'] as const).map((sev) => {
              const isActive = severityFilter === sev;
              let label = sev.toUpperCase();
              if (sev === 'critical') label = 'CRIT';
              if (sev === 'medium') label = 'MED';
              
              let count = scan.total_issues;
              if (sev === 'critical') count = scan.critical_count;
              if (sev === 'high') count = scan.high_count;
              if (sev === 'medium') count = scan.medium_count;
              if (sev === 'low') count = scan.low_count;
 
              let buttonClass = 'text-[9px] font-black rounded px-2.5 py-1.5 transition-all cursor-pointer ';
              if (isActive) {
                buttonClass += 'bg-slate-900 text-white';
              } else {
                buttonClass += 'bg-transparent text-slate-600';
                if (sev === 'critical') buttonClass += ' hover:bg-red-50 hover:text-red-500 text-red-500';
                if (sev === 'high') buttonClass += ' hover:bg-orange-50 hover:text-orange-500 text-orange-500';
                if (sev === 'medium') buttonClass += ' hover:bg-yellow-50 hover:text-yellow-600 text-yellow-600';
                if (sev === 'low') buttonClass += ' hover:bg-sky-50 hover:text-sky-600 text-sky-500';
                if (sev === 'all') buttonClass += ' hover:bg-slate-200';
              }
 
              return (
                <button
                  key={sev}
                  onClick={() => setSeverityFilter(sev)}
                  className={buttonClass}
                >
                  {label} ({count})
                </button>
              );
            })}
          </div>
          
          {/* Search inputs */}
          <div className="flex flex-col sm:flex-row gap-3 flex-grow lg:max-w-xl">
            <select 
              value={scannerFilter}
              onChange={(e) => setScannerFilter(e.target.value)}
              className="cartoon-input focus:outline-none text-xs font-extrabold text-slate-700 bg-white px-3 py-1.5 border-4 cursor-pointer"
            >
              <option value="all">ALL ENGINE FINDINGS</option>
              <option value="bandit">BANDIT RULES</option>
              <option value="semgrep">SEMGREP RULES</option>
            </select>
            
            <div className="relative flex-grow">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400 pointer-events-none">
                <Search className="w-4 h-4" />
              </span>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search threats by path or keyword..."
                className="cartoon-input w-full pl-9 bg-white text-xs text-slate-800 px-3 py-1.5 border-4 focus:outline-none"
              />
            </div>
          </div>
          
        </div>
      </div>

      {/* Findings registry list */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-black text-slate-800 uppercase tracking-widest flex items-center gap-1.5">
            <AlertTriangle className="w-4.5 h-4.5 text-primary" />
            Vulnerability Registry
          </h3>
          <span className="text-[9px] text-slate-400 font-black font-mono">
            SHOWING {filteredIssues.length} OF {issues.length} THREATS
          </span>
        </div>

        {filteredIssues.length === 0 ? (
          <div className="cartoon-card p-12 text-center bg-white">
            <div className="max-w-sm mx-auto space-y-3">
              <span className="p-3 bg-green-50 text-[#10b981] rounded-xl inline-block border-2 border-slate-900 shadow-[2px_2px_0px_#000]">
                <Trophy className="w-8 h-8" />
              </span>
              <h4 className="text-sm font-black text-slate-800 uppercase tracking-wide">Stage Cleared!</h4>
              <p className="text-xs text-slate-400 font-bold leading-relaxed">
                No vulnerabilities match the active filter criteria.
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {filteredIssues.map((issue) => {
              let badgeColor = 'bg-sky-500';
              if (issue.severity === 'critical') badgeColor = 'bg-error';
              else if (issue.severity === 'high') badgeColor = 'bg-orange-500';
              else if (issue.severity === 'medium') badgeColor = 'bg-yellow-500 text-black';

              return (
                <div 
                  key={issue.id}
                  className={`cartoon-card hover:shadow-[8px_8px_0px_#0f172a] transition-all duration-150 sev-glow-${issue.severity} bg-white`}
                >
                  <details className="group">
                    <summary className="flex flex-col md:flex-row md:items-center justify-between gap-3 font-extrabold text-slate-800 pr-10 py-3.5 pl-4 select-none cursor-pointer list-none relative">
                      <div className="flex flex-wrap items-center gap-2.5">
                        <span className={`cartoon-badge text-[9px] font-black uppercase text-white border-2 border-slate-900 px-2 py-0.5 ${badgeColor}`}>
                          {issue.severity}
                        </span>
                        <div className="text-left">
                          <span className="font-extrabold text-xs tracking-tight text-slate-800 mr-1.5">{issue.fix_title}</span>
                          <span className="text-[10px] font-mono text-slate-400 font-bold break-all">{issue.filepath}:{issue.line_number}</span>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-2 self-start md:self-auto text-[9px] text-slate-400 font-mono font-bold">
                        <span className="bg-slate-100 px-2 py-0.5 rounded border-2 border-slate-900 text-[8px] text-primary font-black uppercase">
                          {issue.scanner}
                        </span>
                        <span>{issue.rule_id}</span>
                      </div>
                      
                      {/* Accordion arrow indicator */}
                      <span className="absolute right-4 top-1/2 -translate-y-1/2 transition-transform duration-200 group-open:rotate-180">
                        <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                        </svg>
                      </span>
                    </summary>
                    
                    <div className="bg-slate-50/50 border-t-4 border-slate-900 p-4 space-y-4 text-xs leading-relaxed text-slate-600">
                      <div className="space-y-1">
                        <h4 className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Threat intel</h4>
                        <p className="text-slate-800 text-xs bg-white p-3 rounded-lg border-2 border-slate-900 font-bold">{issue.message}</p>
                      </div>
                      
                      <div className="space-y-1.5">
                        <h4 className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Target code view</h4>
                        <div className="mockup-code bg-slate-900 text-sky-200 text-[10px] p-4 rounded-xl border-2 border-slate-900 overflow-x-auto leading-relaxed max-w-full">
                          <pre data-prefix="line" className="text-slate-550 border-r border-slate-800 pr-2 mr-2 inline-block">Loc: {issue.filepath}:{issue.line_number}</pre>
                          <pre className="whitespace-pre overflow-x-auto mt-2 bg-slate-950 p-2 rounded"><code>{issue.code_snippet}</code></pre>
                        </div>
                      </div>

                      <div className="space-y-3 pt-2">
                        <div>
                          <h4 className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Blueprint Remediation</h4>
                          <p className="text-[11px] text-slate-500 font-bold mt-1">{issue.fix_description}</p>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div className="space-y-1">
                            <div className="text-[10px] font-black text-error flex items-center gap-1">
                              <XCircle className="w-3.5 h-3.5" /> Before (Vulnerable Code)
                            </div>
                            <pre className="bg-red-50 border-2 border-red-200 text-red-700 text-[10px] p-3 rounded-xl font-mono overflow-x-auto leading-relaxed font-bold"><code>{issue.fix_before}</code></pre>
                          </div>
                          <div className="space-y-1">
                            <div className="text-[10px] font-black text-success flex items-center gap-1">
                              <CheckCircle className="w-3.5 h-3.5 text-[#10b981]" /> After (Secured Fix)
                            </div>
                            <pre className="bg-green-50 border-2 border-green-200 text-green-700 text-[10px] p-3 rounded-xl font-mono overflow-x-auto leading-relaxed font-bold"><code>{issue.fix_after}</code></pre>
                          </div>
                        </div>
                      </div>
                      
                      {issue.doc_url && (
                        <div className="flex justify-end pt-2">
                          <a 
                            href={issue.doc_url} 
                            target="_blank" 
                            rel="noopener noreferrer" 
                            className="cartoon-btn cartoon-btn-sm bg-slate-900 text-white px-2.5 py-1 text-[9px] gap-1 flex items-center justify-center"
                          >
                            <ExternalLink className="w-2.5 h-2.5" /> Advisory docs
                          </a>
                        </div>
                      )}
                    </div>
                  </details>
                </div>
              );
            })}
          </div>
        )}
      </div>
      
    </div>
  );
}

export default function ResultsPage() {
  return (
    <Suspense fallback={
      <div className="flex flex-col items-center justify-center py-24 w-full">
        <Loader2 className="w-10 h-10 text-primary animate-spin" />
        <p className="text-xs text-slate-500 font-bold mt-2 font-mono">Loading terminal records...</p>
      </div>
    }>
      <ResultsClient />
    </Suspense>
  );
}
