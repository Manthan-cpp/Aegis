import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

// Authentication is available globally, but no page is protected yet.
// This preserves the guest path while preparing DMs and community routes.
const clerkConfigured = Boolean(
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY && process.env.CLERK_SECRET_KEY,
);

// Keep the existing app available before the user adds Clerk keys.
const authMiddleware = clerkConfigured ? clerkMiddleware() : () => NextResponse.next();

export default authMiddleware;

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|png|jpg|jpeg|gif|svg|ttf|woff2?|ico|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
