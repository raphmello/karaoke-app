import { defineConfig } from "@playwright/test";

// For now the tests cover the player's rules (lyrics timing, key names) and need no browser.
export default defineConfig({ testDir: "tests" });
