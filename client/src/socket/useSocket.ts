import { useEffect, useRef, useState } from "react";
import { io, Socket } from "socket.io-client";
import type { LiveStep } from "../types";

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || "";

let sharedSocket: Socket | null = null;

function getSocket(): Socket {
  if (!sharedSocket) {
    sharedSocket = io(SOCKET_URL, {
      path: "/socket.io",
      transports: ["websocket", "polling"],
    });
  }
  return sharedSocket;
}

/** Subscribe to a run's live reasoning steps. */
export function useLiveRun(runId: string | undefined) {
  const [events, setEvents] = useState<LiveStep[]>([]);
  const [connected, setConnected] = useState(false);
  const [completed, setCompleted] = useState<{ status: string; pr_url?: string } | null>(null);
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    if (!runId) return;
    const socket = getSocket();
    socketRef.current = socket;

    const onConnect = () => {
      setConnected(true);
      socket.emit("subscribe", { run_id: runId });
    };
    const onStep = (e: LiveStep) => {
      if (e.run_id !== runId) return;
      setEvents((prev) => [...prev, e]);
    };
    const onComplete = (e: { run_id: string; status: string; pr_url?: string }) => {
      if (e.run_id !== runId) return;
      setCompleted({ status: e.status, pr_url: e.pr_url });
    };

    socket.on("connect", onConnect);
    socket.on("disconnect", () => setConnected(false));
    socket.on("agent:step", onStep);
    socket.on("run:complete", onComplete);
    if (socket.connected) onConnect();

    return () => {
      socket.emit("unsubscribe", { run_id: runId });
      socket.off("connect", onConnect);
      socket.off("agent:step", onStep);
      socket.off("run:complete", onComplete);
    };
  }, [runId]);

  return { events, connected, completed };
}
