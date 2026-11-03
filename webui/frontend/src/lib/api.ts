const API_BASE = "/api";

async function jsonResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    throw new Error(`API request failed (${res.status} ${res.statusText})`);
  }
  return res.json() as Promise<T>;
}

export interface Profile {
  name: string;
  flight_rule: "vfr" | "ifr";
  filters: string[];
  enabled: boolean;
}

export interface Document {
  id: number;
  name: string;
  profile: string;
  airac_date: string;
  size: number;
  modified: string;
  is_ocr: boolean;
}

export interface RunSummary {
  id: string;
  timestamp: string;
  profiles: string[];
  status: "running" | "success" | "error";
  pdf_created: boolean;
}

export interface UpdateStatus {
  running: boolean;
  run_id: string | null;
  profile?: string;
  stage?: string;
  message?: string;
}

export interface RunDetail {
  id: string;
  timestamp: string;
  logs: Record<string, Array<{ timestamp: string; stage: string; message: string; status: string }>>;
}

export const api = {
  // Profiles
  async getProfiles(): Promise<Profile[]> {
    const data = await jsonResponse<{ profiles: Profile[] }>(
      await fetch(`${API_BASE}/profiles`)
    );
    return data.profiles;
  },

  async createProfile(profile: Omit<Profile, "enabled">): Promise<void> {
    await fetch(`${API_BASE}/profiles`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    });
  },

  async updateProfile(name: string, profile: Profile): Promise<void> {
    await fetch(`${API_BASE}/profiles/${encodeURIComponent(name)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    });
  },

  async cleanup(deleteCache: boolean, deleteOutput: boolean): Promise<void> {
    await fetch(`${API_BASE}/cleanup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ delete_cache: deleteCache, delete_output: deleteOutput }),
    });
  },

  async deleteProfile(name: string): Promise<void> {
    await fetch(`${API_BASE}/profiles/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
  },

  // Documents
  async getDocuments(): Promise<Document[]> {
    const data = await jsonResponse<{ documents: Document[] }>(
      await fetch(`${API_BASE}/documents`)
    );
    return data.documents;
  },

  async deleteDocument(id: number): Promise<void> {
    await fetch(`${API_BASE}/documents/${id}`, {
      method: "DELETE",
    });
  },

  downloadDocument(id: number, filename: string, zip = false): void {
    const a = document.createElement("a");
    a.href = `${API_BASE}/documents/${id}${zip ? "/zip" : ""}`;
    a.download = zip ? filename.replace(/\.pdf$/i, ".zip") : filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  },

  // Runs
  async getRuns(): Promise<RunSummary[]> {
    const res = await fetch(`${API_BASE}/runs`);
    const data = await res.json();
    return data.runs;
  },

  async getRun(runId: string): Promise<RunDetail> {
    const res = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}`);
    if (!res.ok) throw new Error("Run not found");
    return res.json();
  },

  // Update with progress streaming
  async triggerUpdate(options: { profile?: string; force?: boolean } = {}): Promise<{ status: "started" | "already_running" }> {
    const params = new URLSearchParams();
    if (options.profile) params.set("profile", options.profile);
    if (options.force) params.set("force", "true");
    const query = params.toString();
    const res = await fetch(`${API_BASE}/update/run${query ? `?${query}` : ""}`, { method: "POST" });
    if (!res.ok) {
      if (res.status === 409) {
        return { status: "already_running" };
      }
      throw new Error(`Failed to trigger update: ${res.statusText}`);
    }
    const data = await res.json();
    return data;
  },

  async getUpdateStatus(): Promise<UpdateStatus> {
    return jsonResponse<UpdateStatus>(await fetch(`${API_BASE}/update/status`));
  },
};
