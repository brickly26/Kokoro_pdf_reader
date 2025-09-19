import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import * as pdfjsLib from "pdfjs-dist";
// Worker setup for Vite/Electron
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

const API = "http://127.0.0.1:8000";

(pdfjsLib as any).GlobalWorkerOptions.workerSrc = workerUrl;

type Chunk = {
  order_idx: number;
  page_index: number;
  text: string;
  boxes: number[][];
  section?: string;
  start_ms?: number;
  end_ms?: number;
};

type Project = {
  id: string;
  title: string;
  file_path: string;
  file_url?: string;
  merged_audio_path?: string;
  merged_sr?: number;
  chunks: Chunk[];
};

export default function Reader() {
  const { id } = useParams();
  const nav = useNavigate();
  const [proj, setProj] = useState<Project | null>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [activeIdx, setActiveIdx] = useState<number | null>(null);
  const [skipFoot, setSkipFoot] = useState(true);
  const [skipFig, setSkipFig] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [processStatus, setProcessStatus] = useState<{
    status: string;
    progress: number;
    error?: string;
  } | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  const load = async () => {
    const r = await fetch(`${API}/projects/${id}`);
    const d = await r.json();
    if (d.error) {
      alert(d.error);
      return;
    }
    setProj(d);
  };

  const checkStatus = async () => {
    const r = await fetch(`${API}/projects/${id}/status`);
    const status = await r.json();
    setProcessStatus(status);

    if (status.status === "processing") {
      setShowModal(true);
    } else if (status.status === "completed") {
      setShowModal(false);
      await load(); // Reload project data
    } else if (status.status === "failed") {
      setShowModal(false);
      alert(`Audio generation failed: ${status.error || "Unknown error"}`);
    }

    return status;
  };

  useEffect(() => {
    load();
    checkStatus();
  }, [id]);

  useEffect(() => {
    if (processStatus?.status === "processing") {
      const interval = setInterval(checkStatus, 2000);
      return () => clearInterval(interval);
    }
  }, [processStatus?.status]);

  const generate = async () => {
    const r = await fetch(`${API}/projects/${id}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voice: "af_heart", speed: 1.0 }),
    });
    const d = await r.json();
    if (!r.ok || d.error) {
      alert(d.error || "Failed to generate");
      return;
    }
    await load();
  };

  // Render PDF pages using pdf.js
  const canvasContainerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    (async () => {
      if (!proj || !proj.file_url || !canvasContainerRef.current) return;
      const pdf = await (pdfjsLib as any).getDocument(proj.file_url).promise;
      const container = canvasContainerRef.current;
      container.innerHTML = "";
      for (let p = 1; p <= pdf.numPages; p++) {
        const page = await pdf.getPage(p);
        const viewport = page.getViewport({ scale: 1.5 });
        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d")!;
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        canvas.className = "canvasPage";
        container.appendChild(canvas);
        await page.render({ canvasContext: ctx, viewport }).promise;
      }
    })();
  }, [proj?.file_url]);

  // Hover/click overlays via delegated events
  useEffect(() => {
    const container = canvasContainerRef.current;
    if (!container || !proj) return;

    const handlerMove = (ev: MouseEvent) => {
      const target = ev.target as HTMLCanvasElement;
      if (target.tagName !== "CANVAS") {
        setHoverIdx(null);
        return;
      }
      const rect = target.getBoundingClientRect();
      const x = (ev.clientX - rect.left) / 1.5;
      const y = (ev.clientY - rect.top) / 1.5;
      const pageIndex = Array.from(container.children).indexOf(target);
      let hovered: number | null = null;
      for (const c of proj.chunks) {
        if (c.page_index !== pageIndex) continue;
        for (const b of c.boxes) {
          const [x0, y0, x1, y1] = b;
          if (x >= x0 && y >= y0 && x <= x1 && y <= y1) {
            hovered = c.order_idx;
            break;
          }
        }
        if (hovered !== null) break;
      }
      setHoverIdx(hovered);
      drawOverlays();
    };
    const handlerClick = () => {
      if (hoverIdx == null) return;
      playFrom(hoverIdx);
    };

    container.addEventListener("mousemove", handlerMove);
    container.addEventListener("click", handlerClick);
    return () => {
      container.removeEventListener("mousemove", handlerMove);
      container.removeEventListener("click", handlerClick);
    };
  }, [proj, hoverIdx, skipFoot, skipFig]);

  const isFiltered = (c: Chunk) => {
    const s = (c.section || "body").toLowerCase();
    if (skipFoot && (s === "footnote" || s === "page_number")) return true;
    if (skipFig && (s === "figure" || s === "graph" || s === "chart"))
      return true;
    return false;
  };

  const drawOverlays = () => {
    if (!proj || !canvasContainerRef.current) return;
    const container = canvasContainerRef.current;
    for (let p = 0; p < container.children.length; p++) {
      const canvas = container.children[p] as HTMLCanvasElement;
      const ctx = canvas.getContext("2d")!;
      // overlay
      ctx.save();
      ctx.globalAlpha = 0.3;
      for (const c of proj.chunks) {
        if (c.page_index !== p) continue;
        const color =
          activeIdx === c.order_idx
            ? "#70a1ff"
            : hoverIdx === c.order_idx
            ? "#cccccc"
            : null;
        if (!color) continue;
        ctx.fillStyle = color;
        for (const b of c.boxes) {
          const [x0, y0, x1, y1] = b;
          ctx.fillRect(x0 * 1.5, y0 * 1.5, (x1 - x0) * 1.5, (y1 - y0) * 1.5);
        }
      }
      ctx.restore();
    }
  };

  useEffect(() => {
    drawOverlays();
  }, [hoverIdx, activeIdx]);

  const playFrom = (startIdx: number) => {
    if (!proj?.merged_audio_path || !audioRef.current) return;
    let i = startIdx;
    while (i < (proj?.chunks?.length || 0) && isFiltered(proj!.chunks[i])) i++;
    if (i >= (proj?.chunks?.length || 0)) return;
    const c = proj!.chunks[i];
    setActiveIdx(c.order_idx);
    const audio = audioRef.current;
    audio.src = proj!.merged_audio_path!;
    audio.currentTime = (c.start_ms || 0) / 1000;
    audio.play();
    const onTime = () => {
      if (audio.currentTime * 1000 >= (c.end_ms || 0)) {
        audio.pause();
        audio.removeEventListener("timeupdate", onTime);
        playFrom(i + 1);
      }
    };
    audio.addEventListener("timeupdate", onTime);
  };

  if (!proj)
    return (
      <div className="window">
        <div className="toolbar">
          <button className="btn" onClick={() => nav(-1)}>
            Back
          </button>
          <div className="title">Loading…</div>
        </div>
      </div>
    );

  return (
    <div className="window">
      <div className="toolbar">
        <button className="btn" onClick={() => nav(-1)}>
          Back
        </button>
        <div className="title" style={{ marginLeft: 8 }}>
          {proj.title}
        </div>
        <div style={{ flex: 1 }} />
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginLeft: 12,
          }}
        >
          <input
            type="checkbox"
            checked={skipFoot}
            onChange={(e) => setSkipFoot(e.target.checked)}
          />{" "}
          Skip Footnotes/Page Numbers
        </label>
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginLeft: 12,
          }}
        >
          <input
            type="checkbox"
            checked={skipFig}
            onChange={(e) => setSkipFig(e.target.checked)}
          />{" "}
          Skip Figures/Charts/Graphs
        </label>
      </div>
      <div className="pdf">
        <div className="right" ref={canvasContainerRef} />
      </div>
      <audio ref={audioRef} />

      {/* Processing Modal */}
      {showModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0,0,0,0.7)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: "var(--panel)",
              borderRadius: "14px",
              padding: "24px",
              minWidth: "300px",
              textAlign: "center",
              border: "1px solid var(--panel-strong)",
            }}
          >
            <h3 style={{ margin: "0 0 16px 0" }}>Generating Audio</h3>
            <div
              style={{
                width: "100%",
                height: "8px",
                backgroundColor: "var(--panel-strong)",
                borderRadius: "4px",
                overflow: "hidden",
                marginBottom: "16px",
              }}
            >
              <div
                style={{
                  width: `${processStatus?.progress || 0}%`,
                  height: "100%",
                  backgroundColor: "var(--accent)",
                  transition: "width 0.3s ease",
                }}
              />
            </div>
            <p
              style={{
                margin: "0",
                color: "var(--text-dim)",
                fontSize: "14px",
              }}
            >
              {processStatus?.progress || 0}% complete
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
