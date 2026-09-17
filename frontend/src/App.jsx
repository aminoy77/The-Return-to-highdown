import { useEffect, useRef, useState } from "react";
import { CLASES, useGame } from "./game.js";

const DIRS = { norte: "Norte", sur: "Sur", este: "Este", oeste: "Oeste" };

function BackendPill({ backend, onRetry }) {
  if (backend.state === "checking")
    return <p className="pill checking"><span className="dot" /> Comprobando backend…</p>;
  if (backend.state === "online")
    return (
      <p className="pill online">
        <span className="dot" /> Backend disponible
        {typeof backend.players === "number" && ` · ${backend.players} en línea`}
      </p>
    );
  return (
    <div className="pill offline">
      <p><span className="dot" /> Backend no disponible ({backend.detail})</p>
      <button type="button" className="btn ghost" onClick={onRetry}>Reintentar</button>
    </div>
  );
}

function Login({ g }) {
  const [mode, setMode] = useState("login");
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");
  const [nombre, setNombre] = useState("");
  const [clase, setClase] = useState("guerrero");

  const submit = (e) => {
    e.preventDefault();
    if (mode === "login") g.login(usuario.trim(), password);
    else g.register(usuario.trim(), password, nombre.trim(), clase);
  };

  return (
    <div className="login-wrap">
      <form className="login-box" onSubmit={submit}>
        <p className="kicker">mud multiplayer en tiempo real · v5.2</p>
        <h1>THE RETURN TO HIGHDOWN</h1>
        <BackendPill backend={g.backend} onRetry={g.recheck} />
        {mode === "login" ? (
          <>
            <input value={usuario} onChange={(e) => setUsuario(e.target.value)} placeholder="Usuario" autoComplete="username" />
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Contraseña" autoComplete="current-password" />
            <button className="btn primary" type="submit">Conectar</button>
            <button className="btn ghost" type="button" onClick={() => setMode("register")}>Nuevo personaje</button>
          </>
        ) : (
          <>
            <input value={usuario} onChange={(e) => setUsuario(e.target.value)} placeholder="Usuario" autoComplete="username" />
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Contraseña (mín. 4)" autoComplete="new-password" />
            <input value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Nombre de personaje" />
            <select value={clase} onChange={(e) => setClase(e.target.value)}>
              {CLASES.map(([v, label]) => (
                <option key={v} value={v}>{label}</option>
              ))}
            </select>
            <button className="btn primary" type="submit">Crear personaje</button>
            <button className="btn ghost" type="button" onClick={() => setMode("login")}>Ya tengo cuenta</button>
          </>
        )}
        {g.loginError && <p className="form-error">{g.loginError}</p>}
      </form>
    </div>
  );
}

function Room({ g }) {
  const r = g.room;
  if (!r) return <section className="room"><h2>Cargando sala…</h2></section>;
  return (
    <section className="room">
      <div className="room-head">
        <h2>{r.nombre}</h2>
        <button className="btn small" onClick={() => g.command("mirar")}>🔄 Ver</button>
      </div>
      <p className="room-desc">{r.descripcion}</p>
      <div className="flags">
        {r.hospital && <span className="flag hospital">🏥 Hospital</span>}
        {r.tienda && <span className="flag store">🏪 Tienda</span>}
        {r.tesoro && <span className="flag treasure">💎 Tesoro</span>}
        {r.enemigos && <span className="flag enemy">⚠️ Enemigos</span>}
      </div>
      <div className="room-actions">
        {r.enemigos && <button className="btn attack" onClick={() => g.command("atacar")}>⚔️ Atacar</button>}
        {r.hospital && <button className="btn small" onClick={() => g.command("hospital")}>🏥 Curar</button>}
        {r.tienda && <button className="btn small" onClick={() => g.command("tienda")}>🏪 Tienda</button>}
        <button className="btn small" onClick={() => g.command("mochila")}>🎒 Mochila</button>
        <button className="btn small" onClick={() => g.command("ayuda")}>❓ Ayuda</button>
      </div>
      <div className="exits">
        {Object.keys(r.conexiones || {}).map((d) => (
          <button key={d} className="btn exit" onClick={() => g.command(d)}>
            {DIRS[d] || d}
          </button>
        ))}
      </div>
      {r.others ? <p className="others">{r.others}</p> : null}
    </section>
  );
}

function Console({ g }) {
  const [cmd, setCmd] = useState("");
  const boxRef = useRef(null);
  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [g.logs]);
  const send = (e) => {
    e.preventDefault();
    const c = cmd.trim();
    if (!c) return;
    g.command(c);
    setCmd("");
  };
  return (
    <section className="console">
      <div className="entries" ref={boxRef}>
        {g.logs.map((l) => (
          <div key={l.id} className={"log " + l.kind}>{l.text}</div>
        ))}
      </div>
      <form className="console-input" onSubmit={send}>
        <input value={cmd} onChange={(e) => setCmd(e.target.value)} placeholder="Comando o mensaje…" />
        <button className="btn primary" type="submit">➤</button>
        <button className="btn ghost" type="button" onClick={() => g.command("stats")}>Stats</button>
        <button className="btn ghost" type="button" onClick={() => g.command("ranking")}>🏆</button>
      </form>
    </section>
  );
}

function Chat({ g }) {
  const [tab, setTab] = useState("sala");
  const [msg, setMsg] = useState("");
  const boxRef = useRef(null);
  const coolRef = useRef(false);
  const list = g.chats[tab] || [];
  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [list]);
  const send = (e) => {
    e.preventDefault();
    const m = msg.trim();
    if (!m || coolRef.current) return;
    coolRef.current = true;
    g.chat(tab, m);
    setMsg("");
    setTimeout(() => (coolRef.current = false), 1000);
  };
  return (
    <section className="panel">
      <h3>💬 Chat</h3>
      <div className="tabs">
        <button className={tab === "sala" ? "tab active" : "tab"} onClick={() => setTab("sala")}>Sala</button>
        <button className={tab === "global" ? "tab active" : "tab"} onClick={() => setTab("global")}>Global</button>
      </div>
      <div className="chat-list" ref={boxRef}>
        {list.map((c) => (
          <div key={c.id} className="chat-msg">
            {c.from ? <strong>[{c.from}] </strong> : null}{c.text}
          </div>
        ))}
      </div>
      <form className="chat-input" onSubmit={send}>
        <input value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="Mensaje…" maxLength={200} />
        <button className="btn primary" type="submit">➤</button>
      </form>
    </section>
  );
}

function Combat({ g }) {
  const c = g.combat;
  useEffect(() => {
    if (!c.active) return;
    const onKey = (e) => {
      if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
      if (["1", "2", "3", "4"].includes(e.key)) g.action(e.key);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [c.active, g]);
  if (!c.active) return null;
  const pct = (hp, max) => Math.max(0, Math.min(100, (hp / (max || 1)) * 100));
  return (
    <div className="overlay">
      <div className="combat">
        <h2>COMBATE</h2>
        <p className="turn">Turno {c.turno}</p>
        {c.player && (
          <div className="combat-self">
            <div className="bar-row"><span>❤️</span><div className="bar"><div className="fill hp" style={{ width: pct(c.player.hp, c.player.hpMax) + "%" }} /></div><span>{c.player.hp}/{c.player.hpMax}</span></div>
            <div className="bar-row"><span>💧</span><div className="bar"><div className="fill mana" style={{ width: pct(c.player.mana, c.player.manaMax) + "%" }} /></div><span>{c.player.mana}/{c.player.manaMax}</span></div>
          </div>
        )}
        <div className="enemies">
          {c.enemies.length === 0 && <p className="victory">🎉 ¡Victoria!</p>}
          {c.enemies.map((e, i) => (
            <div key={i} className="enemy">
              <strong>{e.nombre}</strong>
              <span>{e.hp} / {e.hpMax} HP</span>
              <div className="bar"><div className="fill hp" style={{ width: pct(e.hp, e.hpMax) + "%" }} /></div>
            </div>
          ))}
        </div>
        <div className="combat-btns">
          <button className="btn combat-btn" onClick={() => g.action("1")}>⚔️ Atacar <kbd>1</kbd></button>
          <button className="btn combat-btn" onClick={() => g.action("2")}>✨ Especial <kbd>2</kbd></button>
          <button className="btn combat-btn" onClick={() => g.action("3")}>💤 Pasar <kbd>3</kbd></button>
          <button className="btn combat-btn" onClick={() => g.action("4")}>🎒 Objeto <kbd>4</kbd></button>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const g = useGame();
  const s = g.stats;

  useEffect(() => {
    if (g.screen !== "game" || g.combat.active) return;
    const onKey = (e) => {
      if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
      if (document.querySelector(".modal.open")) return;
      const k = e.key.toLowerCase();
      if (k === "n") g.command("norte");
      else if (k === "s") g.command("sur");
      else if (k === "e") g.command("este");
      else if (k === "o") g.command("oeste");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [g.screen, g.combat.active]); // g estable: solo re-suscribe al cambiar de pantalla/combate

  if (g.screen === "login") return <Login g={g} />;

  return (
    <div className="app">
      <header>
        <h1>THE RETURN TO HIGHDOWN</h1>
        <div className="hud">
          <span className="chip">⭐ Nv{s?.nivel || 1}</span>
          <span className="chip hp">❤️ {s?.hp ?? 0}/{s?.hpMax ?? 1}</span>
          <span className="chip mana">💧 {s?.mana ?? 0}/{s?.manaMax ?? 1}</span>
          <span className="chip gold">💰 {s?.monedas ?? 0}</span>
        </div>
      </header>
      <div className="main">
        <div className="col">
          <Room g={g} />
          <Console g={g} />
        </div>
        <aside className="side">
          <section className="panel">
            <h3>📊 Estadísticas</h3>
            <dl className="kv">
              <div><dt>Nombre</dt><dd>{s?.nombre || "—"}</dd></div>
              <div><dt>Clase</dt><dd>{s?.clase || "—"}</dd></div>
              <div><dt>Nivel</dt><dd>{s?.nivel || 1}</dd></div>
              <div><dt>XP</dt><dd>{s?.xp ?? 0}/{s?.xpMax ?? 150}</dd></div>
              <div><dt>Daño</dt><dd>{s?.danio ?? 0}</dd></div>
            </dl>
          </section>
          <Chat g={g} />
          <section className="panel">
            <h3>🏆 Ranking</h3>
            {g.ranking.map((r, i) => (
              <div key={i} className={i === 0 ? "rank first" : "rank"}>
                <span>{i + 1}. {r[0]}</span><span>Nv.{r[1]}</span>
              </div>
            ))}
            <p className="online">🌐 {g.ranking.length} en línea</p>
          </section>
        </aside>
      </div>
      <Combat g={g} />
      {g.combat.joinRequest && (
        <div className="overlay">
          <div className="modal open">
            <h2>⚔️ Combate multijugador</h2>
            <p>¡{g.combat.joinRequest} necesita ayuda!</p>
            <div className="row">
              <button className="btn primary" onClick={() => g.command("atacar")}>Unirse</button>
              <button className="btn ghost" onClick={() => g.setCombat((c) => ({ ...c, joinRequest: null }))}>Esperar</button>
            </div>
          </div>
        </div>
      )}
      {g.shop && (
        <div className="overlay">
          <div className="modal open">
            <h2>🏪 Tienda</h2>
            <p className="gold">💰 {g.shop.monedas} monedas</p>
            <div className="shop-grid">
              {g.shop.items.map((it) => (
                <button key={it.id} className="shop-item" onClick={() => g.command("comprar " + it.id)}>
                  <span className="emoji">{it.emoji}</span>
                  <span>{it.nombre}</span>
                  <span className="gold">{it.precio}💰</span>
                </button>
              ))}
            </div>
            <button className="btn primary wide" onClick={() => g.setShop(null)}>Cerrar</button>
          </div>
        </div>
      )}
    </div>
  );
}
