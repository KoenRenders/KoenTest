"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { verifyLoginToken } from "@/lib/api";

function VerifyContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState("");

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setError("Geen token gevonden.");
      return;
    }
    verifyLoginToken(token)
      .then((res) => {
        localStorage.setItem("auth_token", res.data.access_token);
        router.push("/");
      })
      .catch(() => setError("Ongeldige of verlopen inloglink."));
  }, [searchParams, router]);

  if (error) {
    return (
      <div className="max-w-sm mx-auto mt-16">
        <div className="card">
          <h1 className="text-2xl font-bold text-red-700 mb-4">Inloggen mislukt</h1>
          <p className="text-gray-600">{error}</p>
          <a href="/login" className="btn-primary mt-4 inline-block">Opnieuw proberen</a>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-sm mx-auto mt-16">
      <div className="card">
        <p className="text-gray-600">Bezig met inloggen…</p>
      </div>
    </div>
  );
}

export default function VerifyPage() {
  return (
    <Suspense>
      <VerifyContent />
    </Suspense>
  );
}
