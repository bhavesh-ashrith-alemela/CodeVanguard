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
          <footer className="footer footer-center p-8 bg-white text-slate-500 border-t-4 border-slate-900 mt-auto text-center flex flex-col items-center justify-center">
            <aside className="space-y-1">
              <div className="flex items-center gap-1.5 font-black text-slate-800 mb-1 justify-center text-sm md:text-base">
                <Shield className="w-5 h-5 text-primary" />
                <span>CodeVanguard</span>
              </div>
              <p className="text-xs font-bold">Quest: Scan. Detect. Secure. In Seconds.</p>
              <p className="text-[9px] mt-1 text-slate-400 font-bold">&copy; 2026 CodeVanguard. All rights reserved.</p>
            </aside>
          </footer>
        </ToastProvider>
      </body>
    </html>
  );
}
