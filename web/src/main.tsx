import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { HostPage } from "./host/HostPage";
import { JoinPage } from "./phone/JoinPage";
import { PhonePage } from "./phone/PhonePage";
import { RoomsPage } from "./rooms/RoomsPage";
import { TvPage } from "./tv/TvPage";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });

/** / (the open rooms), /tv/<code> (a room's TV), /host, /j/<code> (the QR's link) and /m/<code> (the phone).
 *  Anything else, /tv without a room included, goes to the list of rooms. */
function Screen() {
  const [, first, code] = window.location.pathname.replace(/\/+$/, "").split("/");
  if (!first) return <RoomsPage />;
  if (first === "tv" && code) return <TvPage code={code.toUpperCase()} />;
  if (first === "host") return <HostPage />;
  if (first === "j" && code) return <JoinPage code={code} />;
  if (first === "m" && code) return <PhonePage code={code} />;
  window.location.replace("/");
  return null;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Screen />
    </QueryClientProvider>
  </StrictMode>,
);
