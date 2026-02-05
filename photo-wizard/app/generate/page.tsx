"use client";

import { useEffect, useState } from "react";
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

const API_BASE = "http://127.0.0.1:8000";

type GenerationState = "idle" | "generating" | "success" | "error";

type GeneratedImage = {
  imageId: string;
  url: string;
  promptUsed?: string;
};

export default function GeneratePage() {
  const [checkedStorage, setCheckedStorage] = useState(false);
  const [configJson, setConfigJson] = useState<string | null>(null);

  const [generationState, setGenerationState] =
    useState<GenerationState>("idle");
  const [generatedImage, setGeneratedImage] = useState<GeneratedImage | null>(
    null
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const cfg = localStorage.getItem("gen_config");
    setConfigJson(cfg);
    setCheckedStorage(true);
  }, []);

  async function callGenerateConfig() {
    if (!configJson) return;

    setGenerationState("generating");
    setErrorMessage(null);
    setGeneratedImage(null);

    try {
      const payload = JSON.parse(configJson);

      const res = await fetch(`${API_BASE}/generate-from-product-config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data?.detail || "Generation failed");
      }

      setGeneratedImage({
        imageId: data.image_id,
        url: data.view_url,
        promptUsed: data.prompt_used,
      });

      setGenerationState("success");
    } catch (err: any) {
      setGenerationState("error");
      setErrorMessage(err?.message || "Error generating image");
    }
  }

  const handleDownload = () => {
    if (!generatedImage) return;
    const link = document.createElement("a");
    link.href = generatedImage.url;
    link.download = `photoai-${generatedImage.imageId}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleCopy = () => {
    if (!generatedImage) return;
    navigator.clipboard.writeText(generatedImage.imageId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (checkedStorage && !configJson) {
    return (
      <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center px-4">
        <div className="w-full max-w-md rounded-2xl border border-white/10 bg-slate-900 p-8 shadow-[0_1px_0_0_rgba(255,255,255,0.04)]">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-white/10">
            <ImageIcon className="h-7 w-7 text-white" />
          </div>
          <h2 className="text-xl font-semibold">Falta configuración</h2>
          <p className="mt-2 text-sm text-slate-300">
            Volvé a presets y armá la escena antes de generar.
          </p>

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

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto max-w-6xl px-4 py-12">
        {/* Header */}
        <header className="mb-10 text-center">
          <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1 text-xs font-semibold text-slate-200">
            <span className="h-2 w-2 rounded-full bg-white" />
            Step 3 of 3
          </div>

          <h1 className="mt-4 text-3xl font-semibold">
            Generate image
          </h1>
          <p className="mt-2 text-slate-300">
            Generá una foto lista para e-commerce con UI SaaS profesional.
          </p>
        </header>

        <div className="grid gap-6 lg:grid-cols-5">
          {/* Main */}
          <section className="lg:col-span-3">
            <div className="rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-[0_1px_0_0_rgba(255,255,255,0.04)]">
              {generationState === "idle" && (
                <div className="text-center py-10">
                  <button
                    onClick={callGenerateConfig}
                    className="w-full rounded-xl bg-white px-4 py-3 text-sm font-semibold text-slate-950 hover:bg-white/90"
                  >
                    Generate image
                  </button>
                  <p className="mt-3 text-xs text-slate-400">
                    Usa la configuración guardada desde /presets
                  </p>
                </div>
              )}

              {generationState === "generating" && (
                <div className="py-14 text-center">
                  <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-white/10">
                    <LoaderIcon className="h-6 w-6 animate-spin text-white" />
                  </div>
                  <div className="text-base font-semibold">
                    Generando…
                  </div>
                  <div className="mt-2 text-sm text-slate-400">
                    Esto suele tardar pocos segundos.
                  </div>

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
                  <div className="mt-2 text-sm text-red-200">
                    {errorMessage}
                  </div>

                  <button
                    onClick={callGenerateConfig}
                    className="mt-4 w-full rounded-xl bg-white px-4 py-3 text-sm font-semibold text-slate-950 hover:bg-white/90"
                  >
                    Try again
                  </button>
                </div>
              )}

              {generationState === "success" && generatedImage && (
                <div className="space-y-4">
                  <div className="overflow-hidden rounded-xl border border-white/10 bg-black/20">
                    <img
                      src={generatedImage.url}
                      alt="Generated"
                      className="w-full object-contain"
                    />
                  </div>

                  <div className="flex items-center justify-between rounded-xl border border-white/10 bg-black/20 p-3">
                    <code className="text-xs font-medium text-slate-200 break-all">
                      {generatedImage.imageId}
                    </code>
                    <button
                      onClick={handleCopy}
                      className="inline-flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-950 hover:bg-white/90"
                    >
                      {copied ? (
                        <>
                          <CheckIcon className="h-4 w-4" />
                          Copied
                        </>
                      ) : (
                        <>
                          <CopyIcon className="h-4 w-4" />
                          Copy
                        </>
                      )}
                    </button>
                  </div>

                  <div className="flex gap-3">
                    <button
                      onClick={handleDownload}
                      className="flex-1 rounded-xl bg-white py-3 text-sm font-semibold text-slate-950 hover:bg-white/90"
                    >
                      <span className="inline-flex items-center justify-center gap-2">
                        <DownloadIcon className="h-4 w-4" />
                        Download
                      </span>
                    </button>

                    <button
                      onClick={() => window.open(generatedImage.url, "_blank")}
                      className="flex-1 rounded-xl border border-white/15 bg-white/5 py-3 text-sm font-semibold text-white hover:bg-white/10"
                    >
                      Open
                    </button>
                  </div>

                  {generatedImage.promptUsed && (
                    <details className="rounded-xl border border-white/10 bg-black/20 p-4">
                      <summary className="cursor-pointer text-sm font-semibold text-white">
                        Ver prompt usado (debug)
                      </summary>
                      <pre className="mt-3 whitespace-pre-wrap text-xs text-slate-300">
                        {generatedImage.promptUsed}
                      </pre>
                    </details>
                  )}
                </div>
              )}

              <div className="mt-6 flex items-center justify-between">
                <a
                  href="/presets"
                  className="text-sm font-semibold text-slate-300 hover:text-white"
                >
                  ← Back to config
                </a>

                <span className="text-xs text-slate-500">
                  API: {API_BASE}
                </span>
              </div>
            </div>
          </section>

          {/* Sidebar */}
          <aside className="lg:col-span-2 space-y-4">
            <div className="rounded-2xl border border-white/10 bg-slate-900 p-5">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <InfoIcon className="h-4 w-4" />
                Tips
              </div>

              <div className="mt-4 space-y-3">
                {[
                  ["Producto “locked”", "Mantenemos el producto igual y cambiamos sólo entorno."],
                  ["Mejorá el prompt", "Sumá chips + custom_text en presets."],
                  ["Debug rápido", "Revisá el prompt usado que le mandamos a Gemini."],
                ].map(([t, d]) => (
                  <div
                    key={t}
                    className="rounded-xl border border-white/10 bg-black/20 p-4"
                  >
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
