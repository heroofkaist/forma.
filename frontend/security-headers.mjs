export function securityHeaders(development = false) {
  const csp = [
    "default-src 'self'", `script-src 'self' 'unsafe-inline'${development ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'", "font-src 'self'", "img-src 'self' data: blob:",
    `connect-src 'self'${development ? " ws: wss:" : ""}`, "object-src 'self' blob:",
    "frame-src 'self' blob:", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'self'",
  ].join("; ");
  return [
    { key: "Referrer-Policy", value: "no-referrer" },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "Content-Security-Policy", value: csp },
  ];
}
