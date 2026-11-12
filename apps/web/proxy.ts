import { NextResponse, type NextRequest } from "next/server";

// Optimistic check only; the API verifies every request.
export function proxy(req: NextRequest) {
  const hasSession = req.cookies.has("gc_session");
  const { pathname } = req.nextUrl;
  const isAuthPage = pathname === "/login" || pathname === "/signup";
  if (!hasSession && !isAuthPage) return NextResponse.redirect(new URL("/login", req.url));
  if (hasSession && (isAuthPage || pathname === "/"))
    return NextResponse.redirect(new URL("/dashboard", req.url));
  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/login", "/signup", "/onboarding", "/dashboard/:path*", "/agents/:path*", "/business/:path*", "/runs/:path*", "/approvals/:path*"],
};
