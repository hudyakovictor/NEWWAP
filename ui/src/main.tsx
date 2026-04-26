import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { AppProvider } from "./store/appStore";
import { log } from "./debug/logger";
import { runSelfTest } from "./debug/selfTest";
import { startAuditLoop } from "./debug/auditLoop";

log.info("boot", "boot:start", "DEEPUTIN notebook mounting", {
  userAgent: navigator.userAgent,
  viewport: { w: window.innerWidth, h: window.innerHeight },
  pixelRatio: window.devicePixelRatio,
  href: window.location.href,
});

// Hint to the developer (console) about the helpers.
// eslint-disable-next-line no-console
(window as any).deeputin?.help?.();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProvider>
      <App />
    </AppProvider>
  </StrictMode>
);

// Fire boot self-test once the first frame is up so rendering isn't blocked,
// then start the autonomous audit loop that re-checks invariants every minute.
requestAnimationFrame(() => {
  setTimeout(() => {
    runSelfTest()
      .catch((e) => log.error("self_test", "self_test:fatal", "self-test failed", e))
      .finally(() => startAuditLoop(60_000));
  }, 100);
});
