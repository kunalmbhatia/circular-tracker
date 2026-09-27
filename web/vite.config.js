import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Deployed under /app/ alongside the zero-build dashboard at the repo root
// (see .github/workflows/deploy.yml). Change `base` if you deploy this
// standalone instead of side-by-side with the root index.html.
export default defineConfig({
  base: "/app/",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "dist",
  },
});
