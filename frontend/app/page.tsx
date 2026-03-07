"use client";

import Link from "next/link";
import { useAuth0 } from "@auth0/auth0-react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const { isAuthenticated, isLoading } = useAuth0();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.push("/dashboard");
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-lg">Loading...</p>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen gap-4">
      <Link href="/signIn">
        <button className="bg-red-600 text-white px-5 py-2.5 rounded cursor-pointer hover:bg-red-700">
          Sign In
        </button>
      </Link>
      <Link href="/signUp">
        <button className="bg-blue-600 text-white px-5 py-2.5 rounded cursor-pointer hover:bg-blue-700">
          Sign Up
        </button>
      </Link>
    </div>
  );
}