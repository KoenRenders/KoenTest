"use client";
import { useEffect } from "react";
import { trackEvent } from "@/lib/analytics";

// Klein client-eiland om een funnel-event te vuren wanneer een (server-rendered)
// pagina geopend wordt — bv. de betaalresultaat-pagina's. No-op zonder tracker.
export default function TrackOnMount({ event }: { event: string }) {
  useEffect(() => {
    trackEvent(event);
  }, [event]);
  return null;
}
