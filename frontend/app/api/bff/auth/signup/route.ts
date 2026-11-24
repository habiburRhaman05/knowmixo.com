import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { fail, readJson } from "@/lib/bff-response";

export const runtime = "nodejs";

type SignupBody = { email?: string; password?: string; name?: string };

export async function POST(request: Request) {
  try {
    const body = await readJson<SignupBody>(request);
    const { data } = await backend<{ status: string }>("/api/v1/auth/signup", {
      method: "POST",
      body: {
        email: body.email ?? "",
        password: body.password ?? "",
        name: body.name ?? "",
      },
    });
    return NextResponse.json(data, { status: 202 });
  } catch (error) {
    return fail(error);
  }
}
