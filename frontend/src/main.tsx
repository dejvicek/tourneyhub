import "@/i18n";
import "@/index.css";
// The design's fonts, self-hosted (CSP default-src 'self'): Atkinson
// Hyperlegible Next 400 and 700, Big Shoulders 800, in the Latin and Latin
// Extended subsets that English and Czech need.
import "@fontsource/atkinson-hyperlegible-next/latin-400.css";
import "@fontsource/atkinson-hyperlegible-next/latin-ext-400.css";
import "@fontsource/atkinson-hyperlegible-next/latin-700.css";
import "@fontsource/atkinson-hyperlegible-next/latin-ext-700.css";
import "@fontsource/big-shoulders/latin-800.css";
import "@fontsource/big-shoulders/latin-ext-800.css";

import { QueryClient } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter } from "react-router";

import { App } from "@/App";
import { routes } from "@/routes";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("index.html has no #root element");
}

createRoot(root).render(
  <StrictMode>
    <App router={createBrowserRouter(routes)} queryClient={new QueryClient()} />
  </StrictMode>,
);
