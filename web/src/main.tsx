import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { HostPage } from "./host/HostPage";
import { JoinPage } from "./phone/JoinPage";
import { PhonePage } from "./phone/PhonePage";
import { TvPage } from "./tv/TvPage";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });

/** /tv, /host, /j/<code> (the QR's link) and /m/<code> (the phone). */
function Screen() {
  const [, first, code] = window.location.pathname.replace(/\/+$/, "").split("/");
  if (first === "tv") return <TvPage />;
  if (first === "host") return <HostPage />;
  if (first === "j" && code) return <JoinPage code={code} />;
  if (first === "m" && code) return <PhonePage code={code} />;
  return (
    <main className="flex h-full flex-col items-center justify-center gap-4 px-4 text-center">
      <h1 className="text-3xl font-bold">Karaokê</h1>
      <p className="text-zinc-400">Convidados entram pelo QR Code da TV.</p>
      <div className="flex gap-6">
        <a className="text-amber-300 underline" href="/tv">
          TV
        </a>
        <a className="text-amber-300 underline" href="/host">
          Host
        </a>
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Screen />
    </QueryClientProvider>
  </StrictMode>,
);
