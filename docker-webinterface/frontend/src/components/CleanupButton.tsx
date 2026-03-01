import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { toast } from "sonner";

export function CleanupButton() {
  const [open, setOpen] = useState(false);
  const [deleteCache, setDeleteCache] = useState(false);
  const [deleteOutput, setDeleteOutput] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleCleanup = async () => {
    if (!deleteCache && !deleteOutput) {
        toast.error("Please select at least one option");
        return;
    }
    
    // First click: show confirmation state
    if (!isConfirming) {
        setIsConfirming(true);
        return;
    }

    // Second click: execute
    try {
        setLoading(true);
        await api.cleanup(deleteCache, deleteOutput);
        toast.success("Cleanup successful");
        setOpen(false);
        setIsConfirming(false);
        setDeleteCache(false);
        setDeleteOutput(false);
        // We might want to trigger a refresh of documents/profiles in the parent?
        // But App.tsx controls that. For now, just success message.
        // Ideally we should reload the page or trigger re-fetch.
        // A simple window.location.reload() or exposing a refresh context would work.
        // Since deleting PDFs affects the Documents list immediately.
        setTimeout(() => window.location.reload(), 1000); 
    } catch (e: any) {
        toast.error("Cleanup failed. " + (e.message || ""));
        console.error(e);
        setIsConfirming(false); 
    } finally {
        setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(val) => {
        setOpen(val);
        if (!val) setIsConfirming(false);
    }}>
      <DialogTrigger asChild>
        <Button variant="outline" size="icon" title="Cleanup Storage">
          <Trash2 className="h-5 w-5" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Cleanup Storage</DialogTitle>
          <DialogDescription>
             Select items to delete from the server.
          </DialogDescription>
        </DialogHeader>
        
        <div className="grid gap-4 py-4">
          <div className="flex items-center space-x-2">
            <input 
                type="checkbox" 
                id="cache" 
                className="h-4 w-4 rounded border-gray-300"
                checked={deleteCache}
                onChange={(e) => setDeleteCache(e.target.checked)}
            />
            <label htmlFor="cache" className="text-sm font-medium leading-none cursor-pointer">
              Clear API Cache (Forces re-download)
            </label>
          </div>
          <div className="flex items-center space-x-2">
            <input 
                type="checkbox" 
                id="output" 
                className="h-4 w-4 rounded border-gray-300"
                checked={deleteOutput}
                onChange={(e) => setDeleteOutput(e.target.checked)}
            />
            <label htmlFor="output" className="text-sm font-medium leading-none cursor-pointer">
              Delete All Generated PDFs
            </label>
          </div>
        </div>

        <DialogFooter>
            {isConfirming ? (
                 <div className="flex items-center gap-2 w-full justify-between animate-in fade-in slide-in-from-right-4 duration-300">
                    <span className="text-red-500 text-sm font-bold">Are you sure?</span>
                    <div className="flex gap-2">
                        <Button variant="ghost" onClick={() => setIsConfirming(false)}>Cancel</Button>
                        <Button variant="destructive" onClick={handleCleanup} disabled={loading}>
                            {loading ? "Cleaning..." : "Confirm Delete"}
                        </Button>
                    </div>
                 </div>
            ) : (
                <Button onClick={handleCleanup} disabled={loading || (!deleteCache && !deleteOutput)}>
                    Start Cleanup
                </Button>
            )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
