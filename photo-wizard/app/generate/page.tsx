"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircleIcon,
  CheckIcon,
  CopyIcon,
  DownloadIcon,
  ImageIcon,
  InfoIcon,
  LoaderIcon,
  SparklesIcon,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

type GenerationState = "idle" | "generating" | "success" | "error";

type GeneratedImage = {
  imageId: string;
  url: string;
  promptUsed?: string;
  role?: "hero" | "match";
  index?: number;
  qc?: any;
  attempts?: number;
  shotHint?: string;
};

function safeJsonParse<T>(s: string | null): { ok: true; value: T } | { ok: false; error: string } {
  if (!s) return { ok: false, error: "Missing config" };
  try {
    return { ok: true, value: JSON.parse(s) as T };
  } catch {
    return { ok: false, error: "Invalid JSON in localStorage gen_config" };
  }
}

export default function GeneratePage() {
  const [checkedStorage, setCheckedStorage] = useState(false);
  const [configJson, setConfigJson] = useState<string | null>(null);

  const [generationState, setGenerationState] = useState<GenerationState>("idle");
  const [generatedImages, setGeneratedImages] = useState<GeneratedImage[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    const cfg = localStorage.getItem("gen_config");
    setConfigJson(cfg);
    setCheckedStorage(true);
  }, []);

  const parsed = useMemo(() => safeJsonParse<any>(configJson), [configJson]);

  async function callGeneratePack() {
    if (!parsed.ok) return;

    setGenerationState("generating");
    setErrorMessage(null);
    setGeneratedImages([]);

    try {
      const payload = { ...parsed.value, n: 5 };

      const res = await fetch(`${API_BASE}/generate-pack`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();

      if (!res.ok) throw new Error(data?.detail || "Generation failed");

      const imgs: GeneratedImage[] = (data.images || []).map((x: any) => ({
        imageId: x.image_id,
        url: x.view_url,
        promptUsed: x.prompt_used,
        role: x.role,
        index: x.index,
        qc: x.qc,
        attempts: x.attempts,
        shotHint: x.shot_hint,
      }));

      // HERO first
      imgs.sort((a, b) => (a.index || 999) - (b.index || 999));

      setGeneratedImages(imgs);
      setGenerationState("success");
    } catch (err: any) {
      setGenerationState("error");
      setErrorMessage(err?.message || "Error generating pack");
    }
  }

  const handleDownload = (img: GeneratedImage) => {
    const link = document.createElement("a");
    link.href = img.url;
    link.download = `photoai-${img.imageId}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleCopy = (img: GeneratedImage) => {
    navigator.clipboard.writeText(img.imageId);
    setCopiedId(img.imageId);
    setTimeout(() => setCopiedId(null), 1800);
  };

  if (checkedStorage && !configJson) {
    return (
      <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center px-4">
        <div className="w-full max-w-md rounded-2xl border border-white/10 bg-slate-900 p-8">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-white/10">
            <ImageIcon className="h-7 w-7 text-white" />
          </div>
          <h2 className="text-xl font-semibold">Falta configuración</h2>
          <p className="mt-2 text-sm text-slate-300">Volvé a presets y armá la escena antes de generar.</p>

          <a
            href="/presets"
            className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-3 text-sm font-semibold text-slate-950 hover:bg-white/90"
          >
            <SparklesIcon className="h-4 w-4" />
            Ir a presets
          </a>
        </div>
      </main>
    );
  }

  if (checkedStorage && configJson && !parsed.ok) {
    return (
      <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center px-4">
        <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-slate-900 p-8">
          <h2 className="text-xl font-semibold">Config inválida</h2>
          <p className="mt-2 text-sm text-slate-300">{parsed.error}</p>
          <a
            href="/presets"
            className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-3 text-sm font-semibold text-slate-950 hover:bg-white/90"
          >
            Volver a presets
          </a>
        </div>
      </main>
    );
  }

  const hero = generatedImages.find((x) => x.role === "hero") || generatedImages[0];

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto max-w-6xl px-4 py-12">
        <header className="mb-10 text-center">
          <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1 text-xs font-semibold text-slate-200">
            <span className="h-2 w-2 rounded-full bg-white" />
            Step 3 of 3
          </div>

          <h1 className="mt-4 text-3xl font-semibold">Generate 5-pack</h1>
          <p className="mt-2 text-slate-300">1 HERO + 4 shots distintos, mismo set real.</p>
        </header>

        <div className="grid gap-6 lg:grid-cols-5">
          <section className="lg:col-span-3">
            <div className="rounded-2xl border border-white/10 bg-slate-900 p-6">
              {generationState === "idle" && (
                <div className="text-center py-10 space-y-3">
                  <button
                    onClick={callGeneratePack}
                    className="w-full rounded-xl bg-white px-4 py-3 text-sm font-semibold text-slate-950 hover:bg-white/90"
                  >
                    Generate 5-pack
                  </button>
                  <p className="text-xs text-slate-400">Mantiene escena/estilo/iluminación y fija set con HERO.</p>
                </div>
              )}

              {generationState === "generating" && (
                <div className="py-14 text-center">
                  <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-white/10">
                    <LoaderIcon className="h-6 w-6 animate-spin text-white" />
                  </div>
                  <div className="text-base font-semibold">Generando pack…</div>
                  <div className="mt-2 text-sm text-slate-400">Puede tardar un toque más porque son 5.</div>

                  <div className="mt-6 h-2 w-full overflow-hidden rounded-full bg-white/10">
                    <div className="h-full w-2/3 animate-pulse rounded-full bg-white" />
                  </div>
                </div>
              )}

              {generationState === "error" && (
                <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
                  <div className="flex items-center gap-2 font-semibold text-red-300">
                    <AlertCircleIcon className="h-4 w-4" />
                    Error al generar
                  </div>
                  <div className="mt-2 text-sm text-red-200">{errorMessage}</div>

                  <button
                    onClick={callGeneratePack}
                    className="mt-4 w-full rounded-xl bg-white px-4 py-3 text-sm font-semibold text-slate-950 hover:bg-white/90"
                  >
                    Try again
                  </button>
                </div>
              )}

              {generationState === "success" && generatedImages.length > 0 && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-white">Your 5-pack</div>
                      <div className="text-xs text-slate-400">La primera es HERO. Las otras son shots distintos del mismo set.</div>
                    </div>

                    <button
                      onClick={callGeneratePack}
                      className="rounded-xl bg-white px-4 py-2.5 text-xs font-semibold text-slate-950 hover:bg-white/90"
                    >
                      Regenerate pack
                    </button>
                  </div>

                  {hero && (
                    <div className="rounded-2xl border border-white/10 bg-black/20 overflow-hidden">
                      <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
                        <div className="text-sm font-semibold text-white">HERO</div>
                        <button
                          onClick={() => handleCopy(hero)}
                          className="inline-flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-950 hover:bg-white/90"
                        >
                          {copiedId === hero.imageId ? (
                            <>
                              <CheckIcon className="h-4 w-4" /> Copied
                            </>
                          ) : (
                            <>
                              <CopyIcon className="h-4 w-4" /> Copy ID
                            </>
                          )}
                        </button>
                      </div>
                      <img src={hero.url} alt="HERO" className="w-full object-contain bg-black/20" />
                      <div className="p-4 flex gap-3">
                        <button
                          onClick={() => handleDownload(hero)}
                          className="flex-1 rounded-xl bg-white py-2.5 text-sm font-semibold text-slate-950 hover:bg-white/90"
                        >
                          <span className="inline-flex items-center justify-center gap-2">
                            <DownloadIcon className="h-4 w-4" /> Download
                          </span>
                        </button>
                        <button
                          onClick={() => window.open(hero.url, "_blank")}
                          className="flex-1 rounded-xl border border-white/15 bg-white/5 py-2.5 text-sm font-semibold text-white hover:bg-white/10"
                        >
                          Open
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="grid gap-4 sm:grid-cols-2">
                    {generatedImages
                      .filter((x) => x.role !== "hero")
                      .map((img, idx) => (
                        <div key={img.imageId} className="rounded-2xl border border-white/10 bg-black/20 overflow-hidden">
                          <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
                            <div className="text-sm font-semibold text-white">Shot {idx + 2}</div>
                            <button
                              onClick={() => handleCopy(img)}
                              className="inline-flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-950 hover:bg-white/90"
                            >
                              {copiedId === img.imageId ? (
                                <>
                                  <CheckIcon className="h-4 w-4" /> Copied
                                </>
                              ) : (
                                <>
                                  <CopyIcon className="h-4 w-4" /> Copy ID
                                </>
                              )}
                            </button>
                          </div>

                          <img src={img.url} alt={`Shot ${idx + 2}`} className="w-full object-contain bg-black/20" />

                          <div className="p-4 space-y-3">
                            <code className="block text-[11px] text-slate-300 break-all">{img.imageId}</code>

                            {img.shotHint && (
                              <div className="text-[11px] text-slate-400">Hint: {img.shotHint}</div>
                            )}

                            <div className="flex gap-3">
                              <button
                                onClick={() => handleDownload(img)}
                                className="flex-1 rounded-xl bg-white py-2.5 text-sm font-semibold text-slate-950 hover:bg-white/90"
                              >
                                <span className="inline-flex items-center justify-center gap-2">
                                  <DownloadIcon className="h-4 w-4" /> Download
                                </span>
                              </button>
                              <button
                                onClick={() => window.open(img.url, "_blank")}
                                className="flex-1 rounded-xl border border-white/15 bg-white/5 py-2.5 text-sm font-semibold text-white hover:bg-white/10"
                              >
                                Open
                              </button>
                            </div>

                            {img.promptUsed && (
                              <details className="rounded-xl border border-white/10 bg-black/10 p-3">
                                <summary className="cursor-pointer text-xs font-semibold text-white">Prompt (debug)</summary>
                                <pre className="mt-2 whitespace-pre-wrap text-[11px] text-slate-300">{img.promptUsed}</pre>
                              </details>
                            )}
                          </div>
                        </div>
                      ))}
                  </div>
                </div>
              )}

              <div className="mt-6 flex items-center justify-between">
                <a href="/presets" className="text-sm font-semibold text-slate-300 hover:text-white">
                  ← Back to config
                </a>
                <span className="text-xs text-slate-500">API: {API_BASE}</span>
              </div>
            </div>
          </section>

          <aside className="lg:col-span-2 space-y-4">
            <div className="rounded-2xl border border-white/10 bg-slate-900 p-5">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <InfoIcon className="h-4 w-4" />
                Tips
              </div>

              <div className="mt-4 space-y-3">
                {[
                  ["Set consistente", "La HERO fija el set y las otras lo replican con encuadres distintos."],
                  ["Shots reales", "No son “variaciones random”: son ángulo / foco / crop como un shoot real."],
                  ["QC estricto", "Si detecta look IA o cambios del producto, reintenta automáticamente."],
                ].map(([t, d]) => (
                  <div key={t} className="rounded-xl border border-white/10 bg-black/20 p-4">
                    <div className="text-sm font-semibold text-white">{t}</div>
                    <div className="mt-1 text-sm text-slate-400">{d}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-900 p-5">
              <div className="text-sm font-semibold">Flujo</div>
              <div className="mt-2 text-sm text-slate-400">
                <span className="font-semibold text-white">/upload</span> →{" "}
                <span className="font-semibold text-white">/presets</span> →{" "}
                <span className="font-semibold text-white">/generate</span>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </main>
  );
}
