import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import "./index.css";
import { AccountSync } from "./components/AccountSync";
import { I18nProvider } from "./i18n";
import { SessionProvider } from "./lib/session";
import { Conversation } from "./pages/Conversation";
import { Results } from "./pages/Results";
import { Onboarding } from "./pages/Onboarding";
import { SignIn } from "./pages/SignIn";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <AccountSync />
        {/* The conversation (/) and the results (/results) share one search session. */}
        <SessionProvider>
          <Routes>
            <Route path="/" element={<Conversation />} />
            <Route path="/results" element={<Results />} />
            <Route path="/welcome" element={<Onboarding />} />
            <Route path="/sign-in" element={<SignIn />} />
            <Route path="*" element={<Conversation />} />
          </Routes>
        </SessionProvider>
      </I18nProvider>
    </BrowserRouter>
  </StrictMode>,
);
