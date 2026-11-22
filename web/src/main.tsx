import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import "./index.css";
import App from "./App";
import { AccountSync } from "./components/AccountSync";
import { I18nProvider } from "./i18n";
import { Onboarding } from "./pages/Onboarding";
import { SignIn } from "./pages/SignIn";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <AccountSync />
        <Routes>
          <Route path="/" element={<App />} />
          <Route path="/welcome" element={<Onboarding />} />
          <Route path="/sign-in" element={<SignIn />} />
          <Route path="*" element={<App />} />
        </Routes>
      </I18nProvider>
    </BrowserRouter>
  </StrictMode>,
);
