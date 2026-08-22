import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { api, type AuthMode, type SetupStatus, type User } from "@/api/client";
import { AppShell } from "@/components/AppShell";
import { HistoryPage } from "@/pages/HistoryPage";
import { JobsPage } from "@/pages/JobsPage";
import { LoginPage } from "@/pages/LoginPage";
import { PresetsPage } from "@/pages/PresetsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SetupPage } from "@/pages/SetupPage";
import { SharedPage } from "@/pages/SharedPage";
import { TranscriptPage } from "@/pages/TranscriptPage";
import { ApiSection } from "@/pages/settings/ApiSection";
import { AppearanceSection } from "@/pages/settings/AppearanceSection";
import { ProvidersSection } from "@/pages/settings/ProvidersSection";
import { StorageSection } from "@/pages/settings/StorageSection";
import { UsersSection } from "@/pages/settings/UsersSection";
import { useJobFeed } from "@/useJobFeed";

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
              <Workspace
                user={user}
                authMode={status.auth_mode}
                onLogout={() => {
                  void logout();
                }}
              />
            )
          }
        />
      </Routes>
    </BrowserRouter>
  );
}

/** Everything behind the gate. The job feed is held here rather than in a page
 *  so that walking to the archive and back does not lose the queue. */
function Workspace({
  user,
  authMode,
  onLogout,
}: {
  user: User;
  authMode: AuthMode;
  onLogout: () => void;
}) {
  const feed = useJobFeed();

  return (
    <AppShell authMode={authMode} onLogout={onLogout}>
      <Routes>
        <Route path="/" element={<JobsPage feed={feed} />} />
        <Route path="/history" element={<HistoryPage feed={feed} />} />
        <Route path="/jobs/:jobId" element={<TranscriptPage />} />

        <Route path="/settings" element={<SettingsPage isAdmin={user.is_admin} />}>
          <Route index element={<Navigate to="users" replace />} />
          <Route path="users" element={<UsersSection me={user} authMode={authMode} />} />
          {/* Registered either way: hiding the link is how it is hidden, and a
              typed address should land somewhere rather than nowhere. */}
          <Route
            path="storage"
            element={user.is_admin ? <StorageSection /> : <Navigate to="../appearance" replace />}
          />
          <Route path="appearance" element={<AppearanceSection />} />
          <Route path="providers" element={<ProvidersSection isAdmin={user.is_admin} />} />
          <Route path="presets" element={<PresetsPage />} />
          <Route path="api" element={<ApiSection isAdmin={user.is_admin} />} />
        </Route>

        {/* The two addresses that moved. A bookmark is not a reason to keep a
            screen, but it is a reason not to answer it with the home page. */}
        <Route
          path="/search"
          element={<Navigate to={`/history${window.location.search}`} replace />}
        />
        <Route path="/presets" element={<Navigate to="/settings/presets" replace />} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
