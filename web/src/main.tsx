import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { TvPage } from "./tv/TvPage";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });

function Screen() {
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path === "/tv") return <TvPage />;
  return (
    <main className="flex h-full flex-col items-center justify-center gap-4 px-4 text-center">
      <h1 className="text-3xl font-bold">Karaokê</h1>
      <p className="text-zinc-400">As telas do celular e do host chegam nas próximas fases.</p>
      <a className="text-amber-300 underline" href="/tv">
        Abrir a TV
      </a>
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
