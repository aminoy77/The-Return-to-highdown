import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./App.css";

// Sin StrictMode: evita doble conexión WS en dev (el server registra sesión por socket).
createRoot(document.getElementById("root")).render(<App />);
