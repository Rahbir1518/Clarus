"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

export default function Dashboard() {
  const { isAuthenticated, isLoading, user, logout } = useAuth0();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/signIn");
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-lg">Loading...</p>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm">{user?.email}</span>
          <button
            onClick={() =>
              logout({ logoutParams: { returnTo: window.location.origin } })
            }
            className="bg-red-600 text-white px-4 py-2 rounded cursor-pointer hover:bg-red-700"
          >
            Logout
          </button>
        </div>
      </div>

      <Link href="/workflow">
        <button className="bg-blue-600 text-white px-5 py-2.5 rounded cursor-pointer hover:bg-blue-700">
          Workflow page
        </button>
      </Link>
    </div>
  );
}