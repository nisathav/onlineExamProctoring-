// Vite settings (the tool that runs the dev server and builds the React app).
// Allows JSX inside .js files and bakes in the API address from VITE_API_URL.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Source files use the .js extension (as in the thesis), so let esbuild parse JSX in .js.
export default defineConfig({
  plugins: [react({ include: /\.(js|jsx)$/ })],
  esbuild: { loader: "jsx", include: /src\/.*\.js$/, exclude: [] },
  optimizeDeps: { esbuildOptions: { loader: { ".js": "jsx" } } },
  server: { port: 3000, host: "0.0.0.0" },
  define: {
    "globalThis.__API_URL__": JSON.stringify(process.env.VITE_API_URL || "http://localhost:8000"),
  },
});
