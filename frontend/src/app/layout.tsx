import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";
import { ToastProvider } from "@/components/ToastProvider";
import { Shield } from "lucide-react";

export const metadata: Metadata = {
  title: "CodeVanguard – Static Application Security Testing (SAST) Tool",
  description: "Scan. Detect. Secure. In Seconds.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-screen flex flex-col font-sans bg-base-200 grid-bg text-base-content">
        <ToastProvider>
          {/* Dynamic Navbar */}
          <Navbar />
          
          {/* Main Content Area */}
          <main className="flex-grow max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 flex flex-col">
            {children}
          </main>
          
          {/* Footer */}
          <footer className="p-6 bg-white border-t-2 border-[#14141A] mt-auto">
            <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-center sm:text-left">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-lg bg-[#D6F25B] border border-[#14141A] flex items-center justify-center">
                  <Shield className="w-3.5 h-3.5 text-[#14141A]" />
                </div>
                <span className="font-black text-sm text-[#14141A]">CodeVanguard</span>
                <span className="text-xs text-[#55555F]">| SAST &amp; Secret Security</span>
              </div>
              <div className="flex items-center gap-6 font-mono text-xs font-bold text-[#14141A]">
                <a href="/status" className="hover:underline">System Status</a>
                <a href="/privacy" className="hover:underline">Data Guarantee</a>
                <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="hover:underline">GitHub</a>
              </div>
              <p className="text-[11px] font-mono text-[#55555F]">&copy; 2026 CodeVanguard. Open-source under MIT.</p>
            </div>
          </footer>
        </ToastProvider>
      </body>
    </html>
  );
}
