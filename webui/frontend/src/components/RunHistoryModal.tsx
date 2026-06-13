import { useState } from "react";
import { api, type RunSummary, type RunDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { HistoryIcon } from "lucide-react";

interface RunHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function RunHistoryModal({ isOpen, onClose }: RunHistoryModalProps) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const loadRuns = async () => {
    setIsLoading(true);
    try {
      const runsData = await api.getRuns();
      setRuns(runsData);
      setSelectedRunId(null);
      setRunDetail(null);
    } catch (e) {
      console.error("Failed to load runs:", e);
    } finally {
      setIsLoading(false);
    }
  };

  const selectRun = async (runId: string) => {
    setSelectedRunId(runId);
    setIsLoading(true);
    try {
      const detail = await api.getRun(runId);
      setRunDetail(detail);
    } catch (e) {
      console.error("Failed to load run detail:", e);
    } finally {
      setIsLoading(false);
    }
  };

  const formatDate = (isoString: string) => {
    return new Date(isoString).toLocaleString();
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-96 overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <HistoryIcon className="h-5 w-5" />
            Run History
          </DialogTitle>
        </DialogHeader>

        {!runDetail ? (
          <div className="space-y-4">
            <Button onClick={loadRuns} disabled={isLoading} className="w-full">
              {isLoading ? "Loading..." : "Load Runs"}
            </Button>

            {runs.length > 0 && (
              <Select value={selectedRunId || ""} onValueChange={selectRun}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a run..." />
                </SelectTrigger>
                <SelectContent>
                  {runs.map((run) => (
                    <SelectItem key={run.id} value={run.id}>
                      {formatDate(run.timestamp)} ({run.profiles.length} profile{run.profiles.length !== 1 ? "s" : ""})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <Button onClick={() => setRunDetail(null)} variant="outline" className="w-full">
              ← Back to Runs
            </Button>

            <div className="space-y-3">
              {Object.entries(runDetail.logs).map(([profileName, messages]) => (
                <Card key={profileName}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">{profileName}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-xs space-y-1 max-h-32 overflow-y-auto font-mono">
                      {[...messages].reverse().map((msg, i) => (
                        <div
                          key={i}
                          className={`${
                            msg.status === "error"
                              ? "text-red-600"
                              : msg.status === "success"
                              ? "text-green-600"
                              : "text-muted-foreground"
                          }`}
                        >
                          <span className="font-semibold">[{msg.stage}]</span> {msg.message}
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
