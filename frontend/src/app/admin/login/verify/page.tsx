"use client";
import { Suspense, useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";

// Magic-links wijzen nu naar /login/verify; deze route blijft als redirect
// bestaan voor oude links en geeft het token mee door.
function Redirect() {
  const router = useRouter();
  const params = useSearchParams();
  useEffect(() => {
    const token = params.get("token");
    router.replace(token ? `/login/verify?token=${encodeURIComponent(token)}` : "/login");
  }, [router, params]);
  return null;
}

export default function AdminVerifyRedirect() {
  return <Suspense><Redirect /></Suspense>;
}
