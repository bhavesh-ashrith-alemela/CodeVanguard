'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Code, Play, Shield, Loader2 } from 'lucide-react';
import { useToast } from '@/components/ToastProvider';
import { fetchApi } from '@/lib/api';

interface Example {
  filename: string;
  badge: string;
  badgeClass: string;
  title: string;
  description: string;
  code: string;
}

const EXAMPLES: Example[] = [
  {
    filename: 'level_1_sqli.py',
    badge: 'CRITICAL BOSS',
    badgeClass: 'bg-error text-white',
    title: 'Level 1: SQL Injection (SQLi)',
    description: 'Uses raw string formatting to inject parameter inputs directly into an SQL execution cursor, allowing arbitrary database extraction.',
    code: `import sqlite3

def authenticate(user, password):
    # VULNERABLE: Direct formatting
    conn = sqlite3.connect("prod.db")
    cursor = conn.cursor()
    query = "SELECT * FROM admin WHERE user='%s' AND pass='%s'" % (user, password)
    cursor.execute(query)
    return cursor.fetchone()`
  },
  {
    filename: 'level_2_command.py',
    badge: 'CRITICAL BOSS',
    badgeClass: 'bg-error text-white',
    title: 'Level 2: Command Injection',
    description: 'Runs terminal operations using `subprocess.Popen` with `shell=True` and raw string inputs, exposing the server to command injection.',
    code: `import subprocess

def run_diagnostic(ip_address):
    # VULNERABLE: shell=True exposes shell command injections
    cmd = f"ping -c 4 {ip_address}"
    status = subprocess.Popen(
        cmd, 
        shell=True, 
        stdout=subprocess.PIPE
    )
    return status.communicate()`
  },
  {
    filename: 'level_3_secrets.py',
    badge: 'HIGH THREAT',
    badgeClass: 'bg-orange-500 text-white',
    title: 'Level 3: Credentials Leak',
    description: 'Stores active database passwords and third-party API secret tokens in plaintext inside raw variables.',
    code: `import requests

DB_PASSWORD = "super_admin_pass_12903_vanguard"
STRIPE_API_TOKEN = "sk_live_51Msz32JDjwiSldl20xOsp"

def fetch_billing_details(user_id):
    headers = {"Authorization": f"Bearer {STRIPE_API_TOKEN}"}
    r = requests.get(f"https://api.stripe.com/v1/customers/{user_id}", headers=headers)
    return r.json()`
  },
  {
    filename: 'level_4_sandbox.py',
    badge: 'HIGH THREAT',
    badgeClass: 'bg-orange-500 text-white',
    title: 'Level 4: Crypto & Deserialization',
    description: 'Employs weak MD5 hashing and dangerous `pickle.loads` deserialization, which opens access for Remote Code Execution.',
    code: `import hashlib
import pickle

def compute_insecure_md5(payload):
    # VULNERABLE: md5 is mathematically broken
    h = hashlib.md5(payload.encode())
    return h.hexdigest()

def unpack_session_data(pickled_data):
    # VULNERABLE: pickle.loads enables arbitrary code execution
    return pickle.loads(pickled_data)`
  }
];

export default function ExamplesPage() {
  const router = useRouter();
  const { showToast } = useToast();
  
  const [activeScanIndex, setActiveScanIndex] = useState<number | null>(null);

  const runExampleScan = async (index: number, codeContent: string) => {
    setActiveScanIndex(index);
    showToast("Triggering static scan sequence...", "info");

    try {
      const formData = new FormData();
      formData.append('code', codeContent);

      const response = await fetchApi('/api/scan/json', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Trigger example scan failed.");
      }

      const result = await response.json();
      showToast("Vulnerability analysis queue triggered!", "success");

      setTimeout(() => {
        router.push(`/results?id=${result.scan_id}`);
      }, 1000);

    } catch (error: any) {
      showToast(error.message || "Failed to trigger scan.", "error");
      setActiveScanIndex(null);
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-8 animate-slide-up w-full text-slate-800">
      
      {/* Title Section */}
      <div className="border-b-4 border-slate-900 pb-4 text-center sm:text-left">
        <h2 className="text-xl font-black text-slate-800 flex items-center justify-center sm:justify-start gap-1.5 uppercase tracking-wide">
          <Code className="w-5 h-5 text-primary" />
          Vulnerable Code Examples
        </h2>
        <p className="text-xs text-slate-400 font-bold mt-1">
          Quickly trigger scans using typical security flaw snippets. Click "Scan Example" to execute a live SAST assessment and view fix recommendations.
        </p>
      </div>

      {/* Gallery Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {EXAMPLES.map((ex, index) => {
          const isScanning = activeScanIndex === index;

          return (
            <div key={index} className="cartoon-card flex flex-col justify-between bg-white">
              <div className="window-header bg-slate-900 text-white flex items-center justify-between px-4 py-2 border-b-4 border-slate-900 select-none">
                <span className="text-[9px] font-black uppercase tracking-widest font-mono text-slate-300">{ex.filename}</span>
                <span className={`cartoon-badge border-2 border-slate-900 text-[8px] px-1.5 shadow-none ${ex.badgeClass}`}>
                  {ex.badge}
                </span>
              </div>
              
              <div className="p-6 space-y-4 flex-grow flex flex-col justify-between bg-white">
                <div className="space-y-2">
                  <h3 className="font-black text-slate-800 text-sm uppercase">{ex.title}</h3>
                  <p className="text-xs text-slate-500 font-bold leading-relaxed">
                    {ex.description}
                  </p>
                  <pre className="bg-slate-900 p-4 rounded-xl text-[10px] font-mono text-sky-200 border-2 border-slate-900 overflow-x-auto h-44">
                    <code>{ex.code}</code>
                  </pre>
                </div>
                
                <div className="pt-2">
                  <button 
                    disabled={activeScanIndex !== null}
                    onClick={() => runExampleScan(index, ex.code)}
                    className="cartoon-btn w-full py-2.5 rounded-xl text-xs font-black flex items-center justify-center gap-1.5 cursor-pointer"
                  >
                    {isScanning ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Triggering Scan...
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4" />
                        Scan {ex.title.replace(/Level \d: /, '')}
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
