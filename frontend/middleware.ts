import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/session";

/**
 * Route protection: everything under the authenticated app shell requires a
 * session cookie; everything in the auth group redirects to /overview if
 * already signed in. We only check for presence; the backend remains
 * authoritative on validity, which is checked on the very next data call.
 */
const AUTH_GROUP = [
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password",
  // /verify-email is intentionally left open -- the token comes by email and
  // the page may be opened by a user who is NOT currently signed in.
];

const PROTECTED_PREFIXES = [
  "/overview",
  "/onboarding",
  "/knowledge",
  "/chatbot",
  "/conversations",
  "/usage",
  "/settings",
];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE)?.value);

  if (!hasSession && PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  if (hasSession && AUTH_GROUP.includes(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = "/overview";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  // Skip everything that must be reachable without a session: the Next.js
  // build chunks, any API route, the visitor-facing hosted chat and widget
  // iframe, the embed script itself and static assets.
  matcher: [
    "/((?!_next/|api/|chat/|widget/|embed\\.js$|favicon.ico|robots.txt|sitemap.xml|.*\\.(?:png|jpg|jpeg|svg|gif|ico|webp)$).*)",
  ],
};
