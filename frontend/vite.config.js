import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    // Don't base64-inline the small agent-icon WebPs into the JS chunk:
    // base64 doesn't gzip, and as fingerprinted files under /assets they get
    // the Caddyfile's immutable 1-year cache while the JS chunk churns.
    assetsInlineLimit: 0,
  },
  test: {
    // Pure-function specs run in node; analytics.spec.js opts into jsdom via
    // a // @vitest-environment pragma at the top of the file.
    environment: "node",
    include: ["src/**/*.spec.js"],
  },
});
