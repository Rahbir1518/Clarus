"use client";

import { Auth0Provider } from "@auth0/auth0-react";
import { useRouter } from "next/navigation";

export default function Auth0ProviderWrapper({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();

  const domain = process.env.NEXT_PUBLIC_AUTH0_DOMAIN!;
  const clientId = process.env.NEXT_PUBLIC_AUTH0_CLIENT_ID!;

  return (
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      authorizationParams={{
        redirect_uri: typeof window !== "undefined" ? window.location.origin : "",
      }}
      onRedirectCallback={(appState) => {
        router.push(appState?.returnTo || "/dashboard");
      }}
    >
      {children}
    </Auth0Provider>
  );
}
