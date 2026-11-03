import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Profile, Document } from "@/lib/api";
import { ProfilesSection } from "@/components/ProfilesSection";
import { DocumentsSection } from "@/components/DocumentsSection";
import { RunHistoryTable } from "@/components/RunHistoryTable";
import { CleanupButton } from "@/components/CleanupButton";
import { useTheme } from "@/lib/theme-context";
import { Button } from "@/components/ui/button";
import { toast, Toaster } from "sonner";
import { Moon, Sun } from "lucide-react";

function AppContent() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [running, setRunning] = useState(false);
  const [runsRefresh, setRunsRefresh] = useState(0);
  const wasRunning = useRef(false);
  const { theme, toggleTheme } = useTheme();

  const loadProfiles = async () => {
    setProfiles(await api.getProfiles());
  };

  const loadDocuments = async () => {
    setDocuments(await api.getDocuments());
  };

  const loadDocumentsQuietly = useCallback(() => {
    api.getDocuments().then(setDocuments).catch((error) => console.error("Failed to load documents:", error));
  }, []);

  const pollStatus = useCallback(async () => {
    try {
      const status = await api.getUpdateStatus();
      setRunning(status.running);
      if (wasRunning.current && !status.running) {
        // The update just finished: show the new documents and the finished run without a manual refresh.
        loadDocumentsQuietly();
        setRunsRefresh((n) => n + 1);
      }
      wasRunning.current = status.running;
    } catch (error) {
      console.error("Failed to load update status:", error);
    }
  }, [loadDocumentsQuietly]);

  // Poll quickly while an update is running, slowly otherwise (picks up scheduled runs and other tabs).
  useEffect(() => {
    const first = setTimeout(() => void pollStatus(), 0);
    const id = setInterval(() => void pollStatus(), running ? 2000 : 15000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [running, pollStatus]);

  const handleUpdateStarted = useCallback(() => {
    setRunning(true);
    wasRunning.current = true;
    setRunsRefresh((n) => n + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api.getProfiles()
      .then((loadedProfiles) => {
        if (!cancelled) setProfiles(loadedProfiles);
      })
      .catch((error) => {
        console.error("Failed to load profiles:", error);
        toast.error("Failed to load profiles");
      });
    api.getDocuments()
      .then((loadedDocuments) => {
        if (!cancelled) setDocuments(loadedDocuments);
      })
      .catch((error) => {
        console.error("Failed to load documents:", error);
        toast.error("Failed to load documents");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">DFS AIP Updater</h1>
          <div className="flex items-center gap-2">
            <CleanupButton />
            <Button size="icon" variant="ghost" onClick={toggleTheme}>
              {theme === "light" ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
            </Button>
          </div>
        </header>

        <ProfilesSection profiles={profiles} onProfilesChange={loadProfiles} />
        <DocumentsSection
          documents={documents}
          onDocumentsChange={loadDocuments}
          running={running}
          onUpdateStarted={handleUpdateStarted}
        />
        <RunHistoryTable refreshTrigger={runsRefresh} />
        <Toaster position="top-center" richColors />
      </div>
    </div>
  );
}

export default function App() {
  return <AppContent />;
}
