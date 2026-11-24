/**
 * Local-only process health probe (docker HEALTHCHECK, k8s liveness). Does
 * not touch the backend -- a frontend process is "up" when it can answer
 * JSON. Backend readiness is a separate concern at /health/ready upstream.
 */
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json({ status: "alive" });
}
