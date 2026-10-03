import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { HostPage } from "./host/HostPage";
import { JoinPage } from "./phone/JoinPage";
import { PhonePage } from "./phone/PhonePage";
import { TvPage } from "./tv/TvPage";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });

/** /tv, /host, /j/<code> (the QR's link) and /m/<code> (the phone). Anything else opens the TV (Caddy already
 *  sends the bare address there). */
function Screen() {
  const [, first, code] = window.location.pathname.replace(/\/+$/, "").split("/");
  if (first === "tv") return <TvPage />;
  if (first === "host") return <HostPage />;
  if (first === "j" && code) return <JoinPage code={code} />;
  if (first === "m" && code) return <PhonePage code={code} />;
  window.location.replace("/tv");
  return null;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Screen />
    </QueryClientProvider>
  </StrictMode>,
);
