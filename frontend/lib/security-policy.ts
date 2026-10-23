export function buildContentSecurityPolicy(isNextDevelopment: boolean, isPreview: boolean): string {
  const frameAncestors = isPreview
    ? "'self' https://arena.ai https://*.arena.ai https://*.e2b.app"
    : "'self'";
  const scriptSources = isNextDevelopment
    ? "'self' 'unsafe-inline' 'unsafe-eval'"
    : "'self' 'unsafe-inline'";
  const connectSources = isNextDevelopment ? "'self' ws: wss:" : "'self'";

  return [
    "default-src 'self'",
    `script-src ${scriptSources}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src ${connectSources}`,
    "frame-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    `frame-ancestors ${frameAncestors}`,
  ].join('; ');
}
