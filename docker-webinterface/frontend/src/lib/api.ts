const API_BASE = "/api";

export interface Profile {
  name: string;
  flight_rule: "vfr" | "ifr";
  filters: string[];
  enabled: boolean;
}

export interface Document {
  name: string;
  profile: string;
  airac_date: string;
  path: string;
  size: number;
  modified: string;
  is_ocr: boolean;
}

export interface RunSummary {
  id: string;
  timestamp: string;
  profiles: string[];
  status: "success" | "error";
  pdf_created: boolean;
}

export interface RunDetail {
  id: string;
  timestamp: string;
  logs: Record<string, Array<{ timestamp: string; stage: string; message: string; status: string }>>;
}

export const api = {
  // Profiles
  async getProfiles(): Promise<Profile[]> {
    const res = await fetch(`${API_BASE}/profiles`);
    const data = await res.json();
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
    const res = await fetch(`${API_BASE}/documents`);
    const data = await res.json();
    return data.documents;
  },

  async deleteDocument(profile: string, filename: string): Promise<void> {
    await fetch(`${API_BASE}/documents/${encodeURIComponent(profile)}/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    });
  },

  getDocumentUrl(path: string): string {
    return `${API_BASE}/documents/${path}`;
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
  async triggerUpdate(profile?: string): Promise<{ status: "started" | "already_running" }> {
    const url = profile ? `${API_BASE}/update/run?profile=${encodeURIComponent(profile)}` : `${API_BASE}/update/run`;
    const res = await fetch(url, { method: "POST" });
    if (!res.ok) {
      if (res.status === 409) {
        return { status: "already_running" };
      }
      throw new Error(`Failed to trigger update: ${res.statusText}`);
    }
    const data = await res.json();
    return data;
  },
};
