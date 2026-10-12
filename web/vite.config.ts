import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `pnpm dev` runs outside Docker; the API and the media come from the stack, through Caddy.
const stack = process.env.KARAOKE_STACK ?? "http://localhost:8080"; // another stack to try a branch against

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": stack,
      "/media": stack,
      "/ws": { target: stack, ws: true },
    },
  },
});
