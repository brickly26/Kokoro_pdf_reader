import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

const API = "http://127.0.0.1:8000";

type Project = {
  id: string;
  title: string;
  file_path: string;
  added_at: string;
};

declare global {
  interface Window {
    api?: { openPDF: () => Promise<string | null> };
    electronAPI?: { openPDF: () => Promise<string | null> };
  }
}

export default function Home() {
  const [items, setItems] = useState<Project[]>([]);
  const [busy, setBusy] = useState(false);
  const [hasProcessing, setHasProcessing] = useState(false);
  const nav = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    try {
      const r = await fetch(`${API}/projects`);
      const d = await r.json();
      setItems(d);

      // Check if any projects are still processing
      let anyProcessing = false;
      for (const proj of d) {
        const statusR = await fetch(`${API}/projects/${proj.id}/status`);
        const status = await statusR.json();
        if (status.status === "processing") {
          anyProcessing = true;
          break;
        }
      }
      setHasProcessing(anyProcessing);
    } catch (e) {
      console.error("Failed to load projects", e);
    }
  };

  useEffect(() => {
    load();
    // Poll for processing status updates
    const interval = setInterval(load, 3000);
    return () => clearInterval(interval);
  }, []);

  const createNew = async () => {
    console.log("window.electronAPI:", window.electronAPI);
    console.log("window.api:", window.api);

    // Try electronAPI first (new approach)
    if (window.electronAPI?.openPDF) {
      try {
        const path = await window.electronAPI.openPDF();
        console.log("Selected path:", path);
        if (!path) return;
        await createProject(path);
        return;
      } catch (e) {
        console.error("electronAPI openPDF failed:", e);
      }
    }

    // Try old api approach
    if (window.api?.openPDF) {
      try {
        const path = await window.api.openPDF();
        console.log("Selected path:", path);
        if (!path) return;
        await createProject(path);
        return;
      } catch (e) {
        console.error("IPC openPDF failed:", e);
      }
    }

    // Fallback to hidden file input
    console.log("Using fallback file input");
    fileRef.current?.click();
  };

  const onPickFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    // In Electron, we need an absolute path; the File object may not have it.
    // As a fallback, alert the user to use the native dialog.
    alert("Please use the native file picker. Preload bridge not available.");
  };

  const createProject = async (path: string) => {
    setBusy(true);
    try {
      const r = await fetch(`${API}/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      if (!r.ok) {
        const t = await r.text();
        alert(`Failed to create project: ${t}`);
        return;
      }
      const d = await r.json();
      if (d.error) {
        alert(`Failed to create project: ${d.error}`);
        return;
      }
      if (d.id) {
        await load();
        nav(`/reader/${d.id}`);
      } else {
        alert("Project creation returned no id.");
      }
    } catch (e: any) {
      console.error(e);
      alert(`Failed to create project: ${e?.message || e}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="window">
      <div className="toolbar">
        <div className="title">Kokoro Read‑Along</div>
        <div style={{ flex: 1 }} />
        <button
          className="btn primary"
          onClick={createNew}
          disabled={busy || hasProcessing}
        >
          {busy
            ? "Creating…"
            : hasProcessing
            ? "Processing in background…"
            : "Create New"}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          style={{ display: "none" }}
          onChange={onPickFile}
        />
      </div>
      <div className="list">
        {items.map((p) => (
          <div className="card" key={p.id}>
            <div style={{ fontWeight: 600 }}>{p.title}</div>
            <div
              style={{ color: "var(--text-dim)", fontSize: 12, marginTop: 6 }}
            >
              {p.file_path}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button className="btn" onClick={() => nav(`/reader/${p.id}`)}>
                Open
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
