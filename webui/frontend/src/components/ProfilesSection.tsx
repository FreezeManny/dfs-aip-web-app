import { useState } from "react";
import { api } from "@/lib/api";
import type { Profile } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Check, Copy, FileJson, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

interface ProfilesSectionProps {
  profiles: Profile[];
  onProfilesChange: () => void;
}

export function ProfilesSection({ profiles, onProfilesChange }: ProfilesSectionProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState<Profile | null>(null);
  const [newName, setNewName] = useState("");
  const [newFlightRule, setNewFlightRule] = useState<"vfr" | "ifr">("vfr");
  const [newFilters, setNewFilters] = useState("");
  const [copied, setCopied] = useState(false);

  const handleCopyJson = async () => {
    if (!selectedProfile) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(selectedProfile, null, 2));
      setCopied(true);
      toast.success("Copied JSON to clipboard");
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Failed to copy JSON");
    }
  };

  const handleCreateProfile = async () => {
    if (!newName.trim()) return;
    await api.createProfile({
      name: newName.trim(),
      flight_rule: newFlightRule,
      filters: newFilters
        .split(",")
        .map((f) => f.trim())
        .filter(Boolean),
    });
    setNewName("");
    setNewFilters("");
    setDialogOpen(false);
    onProfilesChange();
  };

  const handleToggleProfile = async (profile: Profile) => {
    await api.updateProfile(profile.name, { ...profile, enabled: !profile.enabled });
    onProfilesChange();
  };

  const handleDeleteProfile = async (name: string) => {
    if (!confirm(`Delete profile "${name}"?`)) return;
    await api.deleteProfile(name);
    onProfilesChange();
  };

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Profiles</CardTitle>
          <div className="flex gap-2">
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm">
                  <Plus className="mr-2 h-4 w-4" /> New Profile
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Create Profile</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 pt-4">
                  <div className="space-y-2">
                    <Label>Name</Label>
                    <Input
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="e.g. VFR Germany"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Flight Rule</Label>
                    <Select value={newFlightRule} onValueChange={(v) => setNewFlightRule(v as "vfr" | "ifr")}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="vfr">VFR</SelectItem>
                        <SelectItem value="ifr">IFR</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Filters (comma-separated)</Label>
                    <Input
                      value={newFilters}
                      onChange={(e) => setNewFilters(e.target.value)}
                      placeholder="e.g. GEN, ENR 3 1-ENR 3 10, AD EDCJ"
                    />
                  </div>
                  <Button onClick={handleCreateProfile} className="w-full">
                    Create
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </CardHeader>
        <CardContent>
          {profiles.length === 0 ? (
            <p className="text-muted-foreground text-center py-4">No profiles yet</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Flight Rule</TableHead>
                  <TableHead>Filters</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {profiles.map((p) => (
                  <TableRow key={p.name}>
                    <TableCell className="font-medium">{p.name}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{p.flight_rule.toUpperCase()}</Badge>
                    </TableCell>
                    <TableCell>
                      {p.filters.length > 0 ? p.filters.join(", ") : <span className="text-muted-foreground">All</span>}
                    </TableCell>
                    <TableCell>
                      <Badge variant={p.enabled ? "default" : "secondary"}>
                        {p.enabled ? "Enabled" : "Disabled"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setSelectedProfile(p)}
                          title="View Profile JSON"
                        >
                          <FileJson className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="w-20"
                          onClick={() => handleToggleProfile(p)}
                        >
                          {p.enabled ? "Disable" : "Enable"}
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => handleDeleteProfile(p.name)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {selectedProfile && (
        <Dialog
          open={!!selectedProfile}
          onOpenChange={(open) => {
            if (!open) {
              setSelectedProfile(null);
              setCopied(false);
            }
          }}
        >
          <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col">
            <DialogHeader className="flex flex-row items-center justify-between pr-8 shrink-0">
              <DialogTitle>Profile JSON - {selectedProfile.name}</DialogTitle>
              <Button size="sm" variant="outline" onClick={handleCopyJson}>
                {copied ? <Check className="mr-2 h-4 w-4" /> : <Copy className="mr-2 h-4 w-4" />}
                {copied ? "Copied" : "Copy"}
              </Button>
            </DialogHeader>
            <pre className="text-sm font-mono bg-muted/50 p-4 rounded overflow-auto flex-1">
              {JSON.stringify(selectedProfile, null, 2)}
            </pre>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
