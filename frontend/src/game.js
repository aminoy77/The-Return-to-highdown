// Núcleo de conexión con el backend Render: URL, health-check y protocolo WS.
// Formas de mensaje del server (server.py): login_ok, register_ok, login_error,
// message, status, sala, combat_start, combat_update, combat_end,
// combat_join_request, chat, ranking, shop, level_up, respawn.
import { useCallback, useEffect, useRef, useState } from "react";

const CLASES = [
  ["guerrero", "⚔️ Guerrero — tanque, alta vida"],
  ["mago", "🔮 Mago — magia poderosa"],
  ["arquero", "🏹 Arquero — ataques rápidos"],
  ["curandero", "💚 Curandero — se cura"],
  ["nigromante", "💀 Nigromante — ataques múltiples"],
  ["hechicero", "✨ Hechicero — magia avanzada"],
  ["caballero", "🛡️ Caballero — equilibrado"],
  ["cazador", "🎯 Cazador — alto daño"],
  ["asesino", "🗡️ Asesino — críticos letales"],
  ["barbaro", "🔥 Bárbaro — daño brutal"],
];

// Prioridad: ?backend= > VITE_BACKEND_URL > local :8080 > mismo origen.
// ?backend= permite apuntar a otro back sin redeploy.
function resolveBackend() {
  const q = new URLSearchParams(window.location.search).get("backend");
  if (q) return q.replace(/\/$/, "");
  const env = import.meta.env.VITE_BACKEND_URL;
  if (env) return String(env).replace(/\/$/, "");
  if (["localhost", "127.0.0.1"].includes(window.location.hostname)) {
    return `${window.location.protocol}//${window.location.hostname}:8080`;
  }
  return window.location.origin;
}

const BACKEND = resolveBackend();
const WS_URL = BACKEND.replace(/^http/, "ws") + "/ws";

async function checkHealth(signal) {
  const r = await fetch(BACKEND + "/api/health", { signal });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

let logId = 0;
const MAX_LOG = 200;
const MAX_CHAT = 50;

export { BACKEND, CLASES };

export function useGame() {
  const [backend, setBackend] = useState({ state: "checking", detail: BACKEND });
  const [screen, setScreen] = useState("login");
  const [loginError, setLoginError] = useState(null);
  const [logs, setLogs] = useState([]);
  const [room, setRoom] = useState(null);
  const [stats, setStats] = useState(null);
  const [chats, setChats] = useState({ sala: [], global: [] });
  const [ranking, setRanking] = useState([]);
  const [combat, setCombat] = useState({ active: false, enemies: [], turno: 1, player: null, joinRequest: null });
  const [shop, setShop] = useState(null);
  const wsRef = useRef(null);
  const credsRef = useRef(null);
  const retryRef = useRef(0);
  const screenRef = useRef(screen);
  screenRef.current = screen; // onclose necesita el valor actual, no el del render que conectó
  const endTimerRef = useRef(null);

  const pushLog = useCallback((text, kind = "info") => {
    setLogs((prev) => [...prev.slice(-MAX_LOG + 1), { id: ++logId, text, kind }]);
  }, []);

  const pushChat = useCallback((scope, from, text) => {
    if (scope !== "sala" && scope !== "global") return;
    setChats((prev) => ({
      ...prev,
      [scope]: [...prev[scope].slice(-MAX_CHAT + 1), { id: ++logId, from, text }],
    }));
  }, []);

  const send = useCallback((obj) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
      return true;
    }
    return false;
  }, []);

  const handleMessage = useCallback(
    (data) => {
      switch (data.type) {
        case "login_ok":
        case "register_ok":
          setScreen("game");
          setLoginError(null);
          pushLog("Bienvenido a The Return to Highdown.", "success");
          break;
        case "login_error":
          setLoginError(data.text || "Error de acceso");
          break;
        case "message":
          pushLog(data.text, "info");
          break;
        case "status":
          setStats(data);
          break;
        case "sala":
          setRoom(data);
          break;
        case "combat_start":
          if (endTimerRef.current) {
            clearTimeout(endTimerRef.current); // pelea nueva antes de que cierre el overlay de la anterior
            endTimerRef.current = null;
          }
          setCombat({
            active: true,
            enemies: data.enemigos || [],
            turno: data.turno || 1,
            player: data.player || null,
            joinRequest: null,
          });
          if (data.joined) pushLog("Te has unido al combate.", "combat");
          else pushLog("¡Combate!", "combat");
          break;
        case "combat_update":
          setCombat((c) => ({
            ...c,
            active: true,
            enemies: data.enemigos || [],
            turno: data.turno || c.turno,
            player: data.player || c.player,
          }));
          break;
        case "combat_end":
          if (data.victory) {
            pushLog(
              `🎉 ¡Victoria! +${data.xp || 0} XP${data.oro ? `, +${data.oro} monedas` : ""}`,
              "loot"
            );
          } else {
            pushLog("💀 Derrota. Todos los jugadores cayeron.", "error");
          }
          if (endTimerRef.current) clearTimeout(endTimerRef.current);
          endTimerRef.current = setTimeout(
            () => setCombat((c) => ({ ...c, active: false, enemies: [] })),
            2000
          );
          break;
        case "combat_join_request":
          setCombat((c) => ({ ...c, joinRequest: data.from || "Alguien" }));
          setTimeout(() => setCombat((c) => ({ ...c, joinRequest: null })), 10000);
          break;
        case "chat":
          pushChat(data.scope, data.from, data.text);
          break;
        case "ranking":
          setRanking(Array.isArray(data.ranking) ? data.ranking : []);
          break;
        case "shop":
          setShop({ items: data.items || [], monedas: data.monedas || 0 });
          break;
        case "level_up":
          pushLog(`🎉 ¡Subiste al nivel ${data.nivel}!`, "success");
          break;
        case "respawn":
          send({ type: "command", cmd: "mirar" });
          break;
        default:
          break;
      }
    },
    [pushChat, pushLog, send]
  );

  const connect = useCallback(
    (onOpen) => {
      const cur = wsRef.current;
      if (cur && cur.readyState === WebSocket.CONNECTING) {
        // Click durante el handshake: encola el auth en vez de perderlo.
        const prev = cur.onopen;
        cur.onopen = (e) => {
          if (prev) prev(e);
          if (onOpen) onOpen();
        };
        return;
      }
      if (cur && cur.readyState === WebSocket.OPEN) {
        if (onOpen) onOpen();
        return;
      }
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onopen = () => {
        retryRef.current = 0;
        setBackend({ state: "online", detail: BACKEND });
        if (onOpen) onOpen();
      };
      ws.onmessage = (e) => {
        try {
          handleMessage(JSON.parse(e.data));
        } catch {
          // Mensaje malformado: se ignora sin romper la sesión.
        }
      };
      ws.onerror = () => ws.close();
      ws.onclose = () => {
        // Reconexión automática solo dentro del juego con credenciales guardadas.
        if (credsRef.current && screenRef.current === "game") {
          pushLog("Conexión perdida. Reconectando…", "error");
          const wait = Math.min(2000 * (retryRef.current + 1), 10000);
          retryRef.current += 1;
          setTimeout(() => {
            const c = credsRef.current;
            if (!c) return;
            connect(() => send({ type: "login", usuario: c.usuario, password: c.password }));
          }, wait);
        }
      };
    },
    [handleMessage, pushLog, send]
  );

  // Health-check inicial: alimenta el indicador del menú de inicio.
  useEffect(() => {
    const ctrl = new AbortController();
    checkHealth(ctrl.signal)
      .then((h) =>
        setBackend({
          state: "online",
          detail: h.message || BACKEND,
          players: h.players,
        })
      )
      .catch(() => setBackend({ state: "offline", detail: BACKEND }));
    return () => ctrl.abort();
  }, []);

  const login = useCallback(
    (usuario, password) => {
      if (!usuario || !password) {
        setLoginError("Introduce usuario y contraseña.");
        return;
      }
      credsRef.current = { usuario, password };
      setLoginError(null);
      connect(() => send({ type: "login", usuario, password }));
    },
    [connect, send]
  );

  const register = useCallback(
    (usuario, password, nombre, clase) => {
      if (!usuario || !password || password.length < 4) {
        setLoginError("Usuario y contraseña de mínimo 4 caracteres.");
        return;
      }
      credsRef.current = { usuario, password };
      setLoginError(null);
      connect(() =>
        send({ type: "register", usuario, password, nombre: nombre || usuario, clase })
      );
    },
    [connect, send]
  );

  const command = useCallback((cmd) => send({ type: "command", cmd }), [send]);
  const action = useCallback((a) => send({ type: "action", action: a }), [send]);
  const chat = useCallback(
    (scope, message) => send({ type: "chat", scope, message }),
    [send]
  );

  // Reintento manual del health-check (botón "Reintentar" del menú).
  const recheck = useCallback(() => {
    setBackend({ state: "checking", detail: BACKEND });
    checkHealth()
      .then((h) =>
        setBackend({ state: "online", detail: h.message || BACKEND, players: h.players })
      )
      .catch(() => setBackend({ state: "offline", detail: BACKEND }));
  }, []);

  return {
    backend,
    recheck,
    screen,
    loginError,
    logs,
    room,
    stats,
    chats,
    ranking,
    combat,
    shop,
    setShop,
    login,
    register,
    command,
    action,
    chat,
    pushLog,
  };
}
