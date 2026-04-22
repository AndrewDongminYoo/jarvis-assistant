// ws.ts — WebSocket client with typed routing and auto-reconnect
type Handler = (msg: Record<string, unknown>) => void;
const handlers = new Map<string, Handler[]>();
let socket: WebSocket | null = null;
let delay = 1000;

export function on(type: string, h: Handler): void {
  if (!handlers.has(type)) handlers.set(type, []);
  handlers.get(type)!.push(h);
}

export function send(msg: Record<string, unknown>): void {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(msg));
}

function dispatch(type: string, msg: Record<string, unknown>): void {
  handlers.get(type)?.forEach((h) => h(msg));
  handlers.get("*")?.forEach((h) => h(msg));
}

export function connect(): void {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${proto}://${location.host}/ws/voice`);

  socket.onopen = () => {
    delay = 1000;
    dispatch("connected", {});
  };
  socket.onclose = () => {
    dispatch("disconnected", {});
    setTimeout(() => {
      delay = Math.min(delay * 2, 30000);
      connect();
    }, delay);
  };
  socket.onerror = () => socket?.close();
  socket.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data as string) as Record<string, unknown>;
      dispatch((msg.type as string) || "unknown", msg);
    } catch {
      /* ignore malformed */
    }
  };
}
