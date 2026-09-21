/**
 * AiMonitorTab — full-page view of the shared AI monitor feed
 * (see stores/aiMonitorStore.ts for the actual polling logic, shared with
 * AiMonitorPopup.tsx so opening both doesn't double the poll rate).
 */
import { useEffect } from "react";
import { useAiMonitorStore } from "@/stores/aiMonitorStore";
import AiMonitorFeed from "./AiMonitorFeed";

export default function AiMonitorTab({ isActive }: { isActive: boolean }) {
  const { feed, loading, error, acquire, release, pollNow, clearFeed } = useAiMonitorStore();

  useEffect(() => {
    if (!isActive) return;
    acquire();
    return () => release();
  }, [isActive, acquire, release]);

  if (!isActive) return null;

  return <AiMonitorFeed feed={feed} loading={loading} error={error} onRetry={pollNow} onClear={clearFeed} />;
}
