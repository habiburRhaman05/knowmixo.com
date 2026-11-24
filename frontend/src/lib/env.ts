/**
 * Centralised environment access. Everything that needs an env var reads
 * through here so a missing one fails loudly on boot instead of producing
 * a baffling runtime error later. No secrets are logged.
 */

function must(key: string): string {
  const value = process.env[key];
  if (!value || value.trim() === "") {
    throw new Error(
      `Missing env var ${key}. Copy frontend/.env.example to frontend/.env.local and fill it in.`
    );
  }
  return value;
}

function optional(key: string, fallback = ""): string {
  const value = process.env[key];
  return value && value.trim() !== "" ? value : fallback;
}

/** Read-only server view. Importing this from a client component is a bug. */
export const serverEnv = {
  backendUrl: () => must("BACKEND_INTERNAL_URL"),
  trustedOriginSecret: () => optional("BFF_TRUSTED_ORIGIN_SECRET"),
  mockBackend: () => optional("MOCK_BACKEND", "false").toLowerCase() === "true",
};

/** Safe to inline in the client bundle. */
export const publicEnv = {
  appUrl: process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000",
  googleClientId: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "",
} as const;
