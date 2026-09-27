import React from "react";
import ReactDOM from "react-dom/client";
import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";
import App from "./App.jsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ThemeProvider attribute="data-theme" defaultTheme="system" enableSystem>
      <App />
      <Toaster position="bottom-center" richColors closeButton />
    </ThemeProvider>
  </React.StrictMode>
);
