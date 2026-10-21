import React from 'react';
import Link from 'next/link';

export type ButtonVariant = 'action' | 'primary' | 'secondary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  href?: string;
  external?: boolean;
  children: React.ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  action: 'bg-[#D6F25B] text-[#14141A] shadow-[3px_3px_0_#14141A] hover:shadow-[1px_1px_0_#14141A] hover:translate-x-[2px] hover:translate-y-[2px]',
  primary: 'bg-[#14141A] text-[#F5F4EE] shadow-[3px_3px_0_#D6F25B] hover:shadow-[1px_1px_0_#D6F25B] hover:translate-x-[2px] hover:translate-y-[2px]',
  secondary: 'bg-[#FFFFFF] text-[#14141A] shadow-[3px_3px_0_#14141A] hover:shadow-[1px_1px_0_#14141A] hover:translate-x-[2px] hover:translate-y-[2px]',
  danger: 'bg-[#FF6B3D] text-white shadow-[3px_3px_0_#14141A] hover:shadow-[1px_1px_0_#14141A] hover:translate-x-[2px] hover:translate-y-[2px]',
  ghost: 'bg-white text-[#14141A] shadow-none hover:bg-[#F5F4EE]'
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'px-3.5 py-1.5 text-xs',
  md: 'px-5 py-2.5 text-sm',
  lg: 'px-6 py-3.5 text-base'
};

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  href,
  external = false,
  disabled = false,
  className = '',
  children,
  ...props
}: ButtonProps) {
  const baseClasses = `inline-flex items-center justify-center gap-2 border-2 border-[#14141A] rounded-full font-bold font-sans tracking-tight transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed select-none ${variantStyles[variant]} ${sizeStyles[size]} ${className}`;

  if (href) {
    if (external) {
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className={baseClasses}
        >
          {loading ? <Spinner /> : children}
        </a>
      );
    }
    return (
      <Link href={href} className={baseClasses}>
        {loading ? <Spinner /> : children}
      </Link>
    );
  }

  return (
    <button
      disabled={disabled || loading}
      className={baseClasses}
      {...props}
    >
      {loading ? <Spinner /> : children}
    </button>
  );
}

function Spinner() {
  return (
    <span className="w-4 h-4 border-2 border-[#14141A] border-t-transparent rounded-full animate-spin flex-shrink-0" />
  );
}
