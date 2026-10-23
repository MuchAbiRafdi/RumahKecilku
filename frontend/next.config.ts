import type { NextConfig } from 'next';
import { buildContentSecurityPolicy } from './lib/security-policy';

const backendOrigin = process.env.BACKEND_ORIGIN || 'http://127.0.0.1:8000';
const previewHost = process.env.NEXT_ALLOWED_DEV_ORIGIN || '*.e2b.app';
const appEnv = process.env.RUMAH_APP_ENV || 'development';
const isPreview = appEnv === 'preview';
// Next dev (including the synthetic preview launcher) needs eval for React's
// cross-environment component-stack reconstruction. Never enable it in production.
const isNextDevelopment = process.env.NODE_ENV !== 'production';
const contentSecurityPolicy = buildContentSecurityPolicy(isNextDevelopment, isPreview);

const globalSecurityHeaders = [
  { key: 'Content-Security-Policy', value: contentSecurityPolicy },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=(), payment=(), usb=()' },
  { key: 'X-DNS-Prefetch-Control', value: 'off' },
  { key: 'Cross-Origin-Resource-Policy', value: 'same-origin' },
  ...(!isPreview ? [{ key: 'X-Frame-Options', value: 'SAMEORIGIN' }] : []),
  ...(appEnv === 'production'
    ? [{ key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' }]
    : []),
];

const nextConfig: NextConfig = {
  allowedDevOrigins: ['localhost', '127.0.0.1', previewHost],
  async headers() {
    return [
      { source: '/:path*', headers: globalSecurityHeaders },
      {
        source: '/api/:path*',
        headers: [
          { key: 'Cache-Control', value: 'no-store, max-age=0' },
          { key: 'Pragma', value: 'no-cache' },
        ],
      },
      {
        source: '/ruang-kerja/:path*',
        headers: [
          { key: 'Cache-Control', value: 'no-store, max-age=0' },
          { key: 'Pragma', value: 'no-cache' },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backendOrigin}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
