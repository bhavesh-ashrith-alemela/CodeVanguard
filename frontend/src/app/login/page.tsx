'use client';

import React, { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { Logo, Button } from '@/components/ui';

function LoginContent() {
  const searchParams = useSearchParams();
  const returnTo = searchParams.get('return_to') || '/dashboard';
  const loginUrl = `/api/auth/github/login?return_to=${encodeURIComponent(returnTo)}`;

  return (
    <div className="w-full max-w-sm mx-auto my-16 px-4">
      <div className="border-2 border-[#14141A] rounded-[18px] bg-white shadow-[5px_5px_0_#14141A] p-8 flex flex-col items-center text-center gap-6">
        <Logo size={48} showWordmark={true} />

        <div className="w-full pt-2">
          <Button
            variant="primary"
            size="lg"
            href={loginUrl}
            className="w-full"
          >
            Continue with GitHub
          </Button>
        </div>

        <p className="font-sans text-xs text-[#55555F] leading-normal m-0">
          Your source code is never stored; repos are scanned in an ephemeral workspace destroyed immediately after the run.
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="text-center py-20 font-mono text-sm">Loading login...</div>}>
      <LoginContent />
    </Suspense>
  );
}
