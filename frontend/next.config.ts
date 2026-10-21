import type { NextConfig } from "next";

const rawBackendUrl =
  process.env.BACKEND_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000';

const backendUrl = rawBackendUrl.replace(/\/+$/, '');

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: '/admin/api/:path*',
        destination: `${backendUrl}/admin/api/:path*`,
      },
      {
        source: '/github/setup',
        destination: `${backendUrl}/github/setup`,
      },
      {
        source: '/webhook',
        destination: `${backendUrl}/webhook`,
      },
    ];
  },
};


export default nextConfig;

