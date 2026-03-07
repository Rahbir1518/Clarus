"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function SignUp() {
  const { loginWithRedirect, isAuthenticated, isLoading } = useAuth0();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;

    if (isAuthenticated) {
      router.push("/dashboard");
      return;
    }

    loginWithRedirect({
      authorizationParams: { screen_hint: "signup" },
      appState: { returnTo: "/dashboard" },
    });
  }, [isLoading, isAuthenticated, loginWithRedirect, router]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <p className="text-lg">Redirecting to signup...</p>
    </div>
  );
}