import { useEffect, useRef, useState } from "react";
import { io, Socket } from "socket.io-client";
import type { LiveStep } from "../types";
import { getRunEvents } from "../api/client";

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || "";
const API_TOKEN = import.meta.env.VITE_API_TOKEN || "";

let sharedSocket: Socket | null = null;

function getSocket(): Socket {
  if (!sharedSocket) {
    sharedSocket = io(SOCKET_URL, {
      path: "/socket.io",
      transports: ["websocket", "polling"],
      auth: API_TOKEN ? { token: API_TOKEN } : undefined,
    });
  }
  return sharedSocket;
}

/** Subscribe to a run's live operational events. */
export function useLiveRun(runId: string | undefined) {
  const [events, setEvents] = useState<LiveStep[]>([]);
  const [connected, setConnected] = useState(false);
  const [completed, setCompleted] = useState<{ status: string; pr_url?: string } | null>(null);
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    if (!runId) return;
    const socket = getSocket();
    socketRef.current = socket;

    const onConnect = async () => {
      setConnected(true);
      socket.emit("subscribe", { run_id: runId });
      try {
        const missed = await getRunEvents(runId, 0);
        setEvents((prev) => {
          const seen = new Set(prev.map((event) => event.sequence).filter(Boolean));
          const restored = missed
            .filter((event) => !seen.has(event.sequence))
            .map((event) => ({ run_id: runId, sequence: event.sequence, type: event.event_type, ...event.payload } as LiveStep));
          return [...prev, ...restored].slice(-500);
        });
      } catch {
        // The authoritative run query still reconciles final state.
      }
    };
    const onStep = (e: LiveStep) => {
      if (e.run_id !== runId) return;
      setEvents((prev) => {
        if (e.sequence && prev.some((item) => item.sequence === e.sequence)) return prev;
        return [...prev, e].slice(-500);
      });
    };
    const onComplete = (e: { run_id: string; status: string; pr_url?: string }) => {
      if (e.run_id !== runId) return;
      setCompleted({ status: e.status, pr_url: e.pr_url });
    };
    const onStatus = (e: LiveStep) => {
      if (e.run_id !== runId) return;
      setEvents((prev) => e.sequence && prev.some((item) => item.sequence === e.sequence) ? prev : [...prev, e].slice(-500));
    };

    socket.on("connect", onConnect);
    socket.on("disconnect", () => setConnected(false));
    socket.on("agent:step", onStep);
    socket.on("run:complete", onComplete);
    socket.on("run:status", onStatus);
    socket.on("run:review", onStatus);
    if (socket.connected) onConnect();

    return () => {
      socket.emit("unsubscribe", { run_id: runId });
      socket.off("connect", onConnect);
      socket.off("agent:step", onStep);
      socket.off("run:complete", onComplete);
      socket.off("run:status", onStatus);
      socket.off("run:review", onStatus);
    };
  }, [runId]);

  return { events, connected, completed };
}
