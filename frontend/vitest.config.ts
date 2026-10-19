import path from "node:path";
import { defineConfig } from "vitest/config";

// NOMICON: reine Funktionstests (Node-Umgebung), Pfad-Alias wie in tsconfig.
export default defineConfig({
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
