/**
 * Server-side session helpers.
 *
 * The backend uses opaque bearer tokens. To keep that token out of browser
 * JavaScript (which would make it a XSS target), the Next.js BFF stores it
 * in an httpOnly, Secure, SameSite=Lax cookie. The browser never sees the
 * token; every BFF route reads it from the cookie and adds `Authorization:
 * Bearer` server-side.
 */
import { cookies } from "next/headers";

export const SESSION_COOKIE = "kmv_session";
export const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7; // 7 days; backend owns the real TTL

type CookieWriter = {
  set: (opts: {
    name: string;
    value: string;
    httpOnly: boolean;
    secure: boolean;
    sameSite: "lax" | "strict" | "none";
    path: string;
    maxAge?: number;
    expires?: Date;
  }) => void;
  delete?: (name: string) => void;
};

function baseOptions() {
  const isProd = process.env.NODE_ENV === "production";
  return {
    name: SESSION_COOKIE,
    httpOnly: true,
    secure: isProd,
    sameSite: "lax" as const,
    path: "/",
  };
}

export function writeSession(jar: CookieWriter, token: string) {
  jar.set({ ...baseOptions(), value: token, maxAge: SESSION_TTL_SECONDS });
}

export function clearSession(jar: CookieWriter) {
  jar.set({ ...baseOptions(), value: "", maxAge: 0, expires: new Date(0) });
}

export async function readSession(): Promise<string | null> {
  const store = await cookies();
  const value = store.get(SESSION_COOKIE)?.value;
  return value && value.length > 0 ? value : null;
}
