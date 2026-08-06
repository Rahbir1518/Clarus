import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

/**
 * Server-side route protection.
 *
 * The app previously had none: `app/(app)/layout.tsx` checked a client-side
 * flag, which is a rendering decision, not a security boundary — the page and
 * its bundle were served to anyone who asked. This runs before the response is
 * produced.
 *
 * It is still not the real access control. The backend verifies its own token
 * on every request and scopes every query to the token's subject; this only
 * decides who gets shown a page. Both layers exist because the failure modes
 * differ: without this, a signed-out visitor sees an app shell that then 401s
 * everywhere.
 *
 * The list is deny-by-default: anything not matched below requires a session,
 * so a new route added under (app) is protected by existing rather than by
 * someone remembering to add it here.
 */
const isPublicRoute = createRouteMatcher([
  "/",
  "/about",
  "/features",
  "/pricing",
  "/signIn(.*)",
  "/signUp(.*)",
]);

export default clerkMiddleware(async (auth, request) => {
  if (!isPublicRoute(request)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // Everything except Next internals and static files, unless a search
    // param is present — those still run so a redirect back from Clerk works.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for Clerk's auto-proxy path.
    "/__clerk/:path*",
    // Always run for API routes.
    "/(api|trpc)(.*)",
  ],
};
