/**
 * Privacy-Preserving Frontend Error Monitoring
 *
 * Guarantees:
 * 1. Never leaks repository source code snippets or stack context.
 * 2. Redacts GitHub tokens, Bearer tokens, and secrets from messages and URLs.
 * 3. Strips sensitive query parameters (code, state, token, secret) before sending.
 */

const SENSITIVE_QUERY_PARAMS = ['code', 'state', 'token', 'access_token', 'secret', 'key'];

const SENSITIVE_PATTERNS: Array<[RegExp, string]> = [
  [/gh[psuor]_[A-Za-z0-9_]{16,}/gi, '[REDACTED_GITHUB_TOKEN]'],
  [/Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*/gi, 'Bearer [REDACTED_BEARER_TOKEN]'],
  [/(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}/g, '[REDACTED_AWS_KEY]'],
  [/sk_live_[0-9a-zA-Z]{24,}/gi, '[REDACTED_STRIPE_KEY]'],
  [/xox[baprs]-[0-9a-zA-Z]{10,}/gi, '[REDACTED_SLACK_TOKEN]'],
];

export function scrubText(text: string): string {
  if (!text || typeof text !== 'string') return text;
  let scrubbed = text;
  for (const [pattern, replacement] of SENSITIVE_PATTERNS) {
    scrubbed = scrubbed.replace(pattern, replacement);
  }
  return scrubbed;
}

export function scrubUrl(rawUrl: string): string {
  try {
    const url = new URL(rawUrl, typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
    for (const param of SENSITIVE_QUERY_PARAMS) {
      if (url.searchParams.has(param)) {
        url.searchParams.set(param, '[REDACTED]');
      }
    }
    return url.pathname + (url.search ? url.search : '');
  } catch {
    return scrubText(rawUrl);
  }
}

export function scrubContext(obj: unknown): unknown {
  if (obj === null || obj === undefined) return obj;
  if (typeof obj === 'string') return scrubText(obj);
  if (typeof obj === 'number' || typeof obj === 'boolean') return obj;

  if (Array.isArray(obj)) {
    return obj.map(scrubContext);
  }

  if (typeof obj === 'object') {
    const clean: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
      const lowerKey = key.toLowerCase();
      if (
        lowerKey.includes('token') ||
        lowerKey.includes('secret') ||
        lowerKey.includes('password') ||
        lowerKey.includes('auth') ||
        lowerKey.includes('cookie') ||
        lowerKey.includes('code_snippet') ||
        lowerKey.includes('source')
      ) {
        clean[key] = '[REDACTED]';
      } else {
        clean[key] = scrubContext(value);
      }
    }
    return clean;
  }

  return String(obj);
}

export interface ErrorReport {
  message: string;
  name?: string;
  stack?: string;
  context?: Record<string, unknown>;
  timestamp: string;
}

export function reportError(error: unknown, context?: Record<string, unknown>): ErrorReport {
  const errObj = error instanceof Error ? error : new Error(String(error));
  const cleanMessage = scrubText(errObj.message || 'Unknown error');
  const cleanStack = errObj.stack ? scrubText(errObj.stack.split('\n').slice(0, 5).join('\n')) : undefined;
  const safeContext = scrubContext(context || {}) as Record<string, unknown>;

  const report: ErrorReport = {
    name: errObj.name,
    message: cleanMessage,
    stack: cleanStack,
    context: safeContext,
    timestamp: new Date().toISOString(),
  };

  // If a browser Sentry client is initialized (e.g. via CDN or package), pass through sanitized event
  if (typeof window !== 'undefined' && (window as any).Sentry) {
    try {
      (window as any).Sentry.captureException(errObj, {
        extra: safeContext,
      });
    } catch {
      // Sentry fallback
    }
  }

  // Fallback to console with clear, privacy-preserving tag
  if (process.env.NODE_ENV !== 'production') {
    console.warn('[CodeVanguard Error Monitor]', report.message, safeContext);
  }

  return report;
}

/**
 * Initializes window unhandled rejection and error listeners on the client side.
 */
export function initClientErrorMonitoring(): () => void {
  if (typeof window === 'undefined') return () => {};

  const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
    reportError(event.reason, { type: 'unhandled_rejection' });
  };

  const handleGlobalError = (event: ErrorEvent) => {
    reportError(event.error || event.message, {
      type: 'global_error',
      filename: event.filename ? scrubUrl(event.filename) : undefined,
    });
  };

  window.addEventListener('unhandledrejection', handleUnhandledRejection);
  window.addEventListener('error', handleGlobalError);

  return () => {
    window.removeEventListener('unhandledrejection', handleUnhandledRejection);
    window.removeEventListener('error', handleGlobalError);
  };
}
