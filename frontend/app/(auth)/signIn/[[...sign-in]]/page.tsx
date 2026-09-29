import { SignIn } from "@clerk/nextjs";

/**
 * Clerk renders and handles the whole flow here. The catch-all segment is
 * required: Clerk routes its own sub-steps (verification, factor two, reset)
 * as child paths of this one.
 *
 * No "use client" — the component is rendered on the server and hydrates
 * itself, so the sign-in form is not gated behind a JS bundle.
 */
export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <SignIn
        signUpUrl="/signUp"
        forceRedirectUrl="/dashboard"
        fallbackRedirectUrl="/dashboard"
      />
    </div>
  );
}
