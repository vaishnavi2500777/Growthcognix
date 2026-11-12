import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  (await cookies()).delete("gc_session");
  return NextResponse.redirect(new URL("/login", req.url));
}
