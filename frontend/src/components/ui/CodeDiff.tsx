'use client';

import React, { useState } from 'react';

interface CodeDiffProps {
  diff: string;
  filename?: string;
  className?: string;
  maxHeight?: string;
}

interface ParsedLine {
  type: 'add' | 'del' | 'context' | 'header';
  oldLineNumber?: number;
  newLineNumber?: number;
  content: string;
}

export function CodeDiff({ diff, filename, className = '', maxHeight = 'max-h-[420px]' }: CodeDiffProps) {
  const [copied, setCopied] = useState(false);

  const lines = diff.split('\n');
  const parsedLines: ParsedLine[] = [];

  let oldCounter = 1;
  let newCounter = 1;
  let addCount = 0;
  let delCount = 0;

  for (const line of lines) {
    if (line.startsWith('@@')) {
      const match = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if (match) {
        oldCounter = parseInt(match[1], 10);
        newCounter = parseInt(match[2], 10);
      }
      parsedLines.push({ type: 'header', content: line });
    } else if (line.startsWith('+++') || line.startsWith('---')) {
      // Diff metadata headers
      parsedLines.push({ type: 'header', content: line });
    } else if (line.startsWith('+')) {
      addCount++;
      parsedLines.push({
        type: 'add',
        newLineNumber: newCounter++,
        content: line.substring(1)
      });
    } else if (line.startsWith('-')) {
      delCount++;
      parsedLines.push({
        type: 'del',
        oldLineNumber: oldCounter++,
        content: line.substring(1)
      });
    } else {
      parsedLines.push({
        type: 'context',
        oldLineNumber: oldCounter++,
        newLineNumber: newCounter++,
        content: line.startsWith(' ') ? line.substring(1) : line
      });
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(diff);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`border-2 border-[#14141A] rounded-xl bg-white shadow-[4px_4px_0px_#14141A] overflow-hidden ${className}`}>
      {/* Header bar */}
      <div className="flex items-center justify-between px-3.5 py-2.5 bg-[#F5F4EE] border-b-2 border-[#14141A] text-xs font-mono font-bold">
        <div className="flex items-center gap-2 overflow-hidden truncate">
          <span className="text-[#14141A] truncate">{filename || 'Unified Diff'}</span>
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="px-1.5 py-0.5 rounded bg-[#D6F25B] text-[#14141A] text-[10px] border border-[#14141A]">
              +{addCount}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-[#FF6B3D] text-white text-[10px] border border-[#14141A]">
              -{delCount}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={handleCopy}
          className="px-2.5 py-1 text-[11px] font-sans font-bold bg-white text-[#14141A] border-2 border-[#14141A] rounded-md shadow-[2px_2px_0px_#14141A] hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[1px_1px_0px_#14141A] transition-all shrink-0 cursor-pointer"
          title="Copy diff to clipboard"
        >
          {copied ? '✓ Copied' : 'Copy diff'}
        </button>
      </div>

      {/* Code viewport with line numbers */}
      <div className={`overflow-x-auto overflow-y-auto font-mono text-xs ${maxHeight}`}>
        <table className="w-full border-collapse">
          <tbody>
            {parsedLines.map((l, idx) => {
              if (l.type === 'header') {
                return (
                  <tr key={idx} className="bg-[#B8A2FF]/15 text-[#55555F] border-y border-[#E2E0D6] select-none">
                    <td colSpan={3} className="py-1 px-4 text-[11px] font-bold">
                      {l.content}
                    </td>
                  </tr>
                );
              }

              const isAdd = l.type === 'add';
              const isDel = l.type === 'del';
              const rowBg = isAdd
                ? 'bg-[#E6F9ED] text-[#14141A]'
                : isDel
                ? 'bg-[#FFE5E7] text-[#14141A]'
                : 'bg-white text-[#14141A] hover:bg-[#F5F4EE]';

              const indicator = isAdd ? '+' : isDel ? '-' : ' ';
              const indicatorColor = isAdd ? 'text-[#1E7E34] font-bold' : isDel ? 'text-[#D93025] font-bold' : 'text-[#8E8E93]';

              return (
                <tr key={idx} className={`${rowBg} transition-colors leading-relaxed`}>
                  {/* Old line number */}
                  <td className="w-10 text-right pr-2 text-[#8E8E93] select-none border-r border-[#E2E0D6] text-[11px]">
                    {l.oldLineNumber || ''}
                  </td>
                  {/* New line number */}
                  <td className="w-10 text-right pr-2 text-[#8E8E93] select-none border-r border-[#E2E0D6] text-[11px]">
                    {l.newLineNumber || ''}
                  </td>
                  {/* Code line */}
                  <td className="pl-3 pr-4 whitespace-pre">
                    <span className={`inline-block w-3 select-none ${indicatorColor}`}>{indicator}</span>
                    <span>{l.content}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
