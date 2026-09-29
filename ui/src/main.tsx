import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { locale } from "./i18n";
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./index.css";

document.documentElement.lang = locale;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
