"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

// Eén gedeelde login-pagina voor iedereen; deze route blijft enkel bestaan als
// redirect zodat oude links/bladwijzers blijven werken.
export default function LedenLoginRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/login"); }, [router]);
  return null;
}
