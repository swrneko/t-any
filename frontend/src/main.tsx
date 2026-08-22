import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { ThemeProvider } from "./components/ThemeProvider";
import { TooltipProvider } from "./components/ui/tooltip";
import "./i18n";
import "./index.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("Root container is missing from index.html");
}

createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      <TooltipProvider delayDuration={300}>
        <App />
      </TooltipProvider>
    </ThemeProvider>
  </StrictMode>,
);
