import { NextResponse } from "next/server";

export function middleware() {
  if (process.env.NODE_ENV !== "development") {
    return new NextResponse("Not found.", {
      status: 404,
      headers: { "Cache-Control": "private, no-store", "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/design-preview/:path*", "/teacher/review-preview/:path*"],
};
