/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: "standalone",
  async headers() {
    // Three header groups:
    //  1. Global baseline — strict, denies framing.
    //  2. /widget/* — the embeddable chat widget. We DROP X-Frame-Options
    //     and add a CSP `frame-ancestors *` (effectively: any site can
    //     embed). The backend's per-bot domain allowlist is the real
    //     frame-restriction check; it runs on the session bootstrap call.
    //  3. /embed.js — the loader script, served with a long cache so repeat
    //     visitors don't re-download it.
    const baseline = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
      {
        key: "Strict-Transport-Security",
        value: "max-age=63072000; includeSubDomains; preload",
      },
    ];
    return [
      {
        source: "/:path((?!widget/|embed\\.js).*)",
        headers: [...baseline, { key: "X-Frame-Options", value: "DENY" }],
      },
      {
        source: "/widget/:publicId*",
        headers: [
          ...baseline,
          { key: "Content-Security-Policy", value: "frame-ancestors *" },
        ],
      },
      {
        source: "/embed.js",
        headers: [
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
          { key: "Cache-Control", value: "public, max-age=300, s-maxage=3600" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
    ];
  },
};

export default nextConfig;
