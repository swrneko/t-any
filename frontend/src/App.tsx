import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { api, type SetupStatus, type User } from "@/api/client";
import { AppShell } from "@/components/AppShell";
import { JobsPage } from "@/pages/JobsPage";
import { LoginPage } from "@/pages/LoginPage";
import { PresetsPage } from "@/pages/PresetsPage";
import { SearchPage } from "@/pages/SearchPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SetupPage } from "@/pages/SetupPage";
import { SharedPage } from "@/pages/SharedPage";
import { TranscriptPage } from "@/pages/TranscriptPage";

export default function App() {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const bootstrap = useCallback(async () => {
    const next = await api.setupStatus();
    setStatus(next);
    if (!next.needs_setup) {
      setUser(await api.me().catch(() => null));
    }
    setReady(true);
  }, []);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  const logout = async () => {
    await api.logout();
    setUser(null);
  };

  if (!ready || !status) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        {/* Outside the gate on purpose: a share link is read by people with no
            account here, and sending them to a login screen defeats the link. */}
        <Route path="/s/:token" element={<SharedPage />} />
        <Route
          path="*"
          element={
            status.needs_setup ? (
              <SetupPage
                onCreated={() => {
                  void bootstrap();
                }}
              />
            ) : !user ? (
              <LoginPage onLoggedIn={setUser} />
            ) : (
              <AppShell
                authMode={status.auth_mode}
                onLogout={() => {
                  void logout();
                }}
              >
                <Routes>
                  <Route path="/" element={<JobsPage />} />
                  <Route path="/jobs/:jobId" element={<TranscriptPage />} />
                  <Route path="/search" element={<SearchPage />} />
                  <Route path="/presets" element={<PresetsPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </AppShell>
            )
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
