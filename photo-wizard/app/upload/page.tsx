"use client";

import React, { useState, useCallback, useRef } from "react";
import {
  ImageIcon,
  UploadCloudIcon,
  XIcon,
  CheckCircle2Icon,
  AlertCircleIcon,
  ArrowRightIcon,
  FileIcon,
  LightbulbIcon,
  CheckIcon,
  CameraIcon,
  SunIcon,
  FrameIcon,
  EraserIcon,
  LoaderIcon,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

type UploadState = "idle" | "dragging" | "uploading" | "success" | "error";

const tips = [
  { icon: CameraIcon, title: "Use high-quality images", description: "Clear, well-lit photos work best for AI processing" },
  { icon: SunIcon, title: "Good lighting matters", description: "Ensure your product is evenly lit without harsh shadows" },
  { icon: FrameIcon, title: "Center your product", description: "Position the product in the middle of the frame" },
  { icon: EraserIcon, title: "Simple backgrounds", description: "Plain or white backgrounds give the best results" },
];

async function uploadProductReal(
  file: File,
  file2: File | null,
  productType: string,
  aesthetic: string
): Promise<{ ok: boolean; product_id?: string; detail?: string; has_secondary?: boolean }> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);

  try {
    const formData = new FormData();
    formData.append("file", file);
    if (file2) formData.append("file2", file2);
    formData.append("product_type", (productType || "").trim());
    formData.append("aesthetic", (aesthetic || "minimalista").trim());

    const res = await fetch(`${API_BASE}/upload-product`, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });

    const contentType = res.headers.get("content-type") || "";
    let data: any = {};
    if (contentType.includes("application/json")) {
      data = await res.json().catch(() => ({}));
    } else {
      const txt = await res.text().catch(() => "");
      data = { detail: txt || "Non-JSON response" };
    }

    if (!res.ok) {
      return { ok: false, detail: data?.detail || `Upload failed (${res.status})` };
    }

    return {
      ok: true,
      product_id: data?.product_id,
      has_secondary: !!data?.has_secondary,
    };
  } catch (e: any) {
    if (e?.name === "AbortError") {
      return { ok: false, detail: "Timeout: el backend tardó demasiado (20s). ¿Está corriendo uvicorn?" };
    }
    return {
      ok: false,
      detail:
        e?.message ||
        "Network/CORS error: no se pudo conectar al backend (revisá que esté en 127.0.0.1:8000 y CORS habilitado).",
    };
  } finally {
    clearTimeout(timeout);
  }
}

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [file2, setFile2] = useState<File | null>(null);

  const [preview, setPreview] = useState<string | null>(null);
  const [preview2, setPreview2] = useState<string | null>(null);

  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [productId, setProductId] = useState<string | null>(null);

  const [productType, setProductType] = useState<string>("");
  const [aesthetic, setAesthetic] = useState<string>("minimalista");

  const inputRef = useRef<HTMLInputElement>(null);
  const inputRef2 = useRef<HTMLInputElement>(null);

  const currentStep = 1;
  const totalSteps = 3;

  const handleFileSelect = useCallback(
    async (selectedFile: File) => {
      if (!selectedFile.type.startsWith("image/")) {
        setErrorMessage("Please upload an image file (JPG, PNG, WebP)");
        setUploadState("error");
        return;
      }

      if (selectedFile.size > 10 * 1024 * 1024) {
        setErrorMessage("File size must be less than 10MB");
        setUploadState("error");
        return;
      }

      setFile(selectedFile);
      setProductId(null);
      setErrorMessage(null);
      setUploadState("uploading");

      const reader = new FileReader();
      reader.onload = (e) => setPreview(e.target?.result as string);
      reader.readAsDataURL(selectedFile);

      const result = await uploadProductReal(selectedFile, file2, productType, aesthetic);

      if (result.ok && result.product_id) {
        setUploadState("success");
        setProductId(result.product_id);
        localStorage.setItem("product_id", result.product_id);
      } else {
        setUploadState("error");
        setErrorMessage(result.detail || "Failed to upload image. Please try again.");
      }
    },
    [file2, productType, aesthetic]
  );

  const handleSecondFileSelect = useCallback(
    async (selectedFile: File) => {
      if (!selectedFile.type.startsWith("image/")) return;
      if (selectedFile.size > 10 * 1024 * 1024) return;

      setFile2(selectedFile);

      const reader = new FileReader();
      reader.onload = (e) => setPreview2(e.target?.result as string);
      reader.readAsDataURL(selectedFile);

      if (file) {
        setErrorMessage(null);
        setUploadState("uploading");

        const result = await uploadProductReal(file, selectedFile, productType, aesthetic);

        if (result.ok && result.product_id) {
          setUploadState("success");
          setProductId(result.product_id);
          localStorage.setItem("product_id", result.product_id);
        } else {
          setUploadState("error");
          setErrorMessage(result.detail || "Failed to upload second image. Please try again.");
        }
      }
    },
    [file, productType, aesthetic]
  );

  const handleRemove = useCallback(() => {
    setFile(null);
    setPreview(null);
    setUploadState("idle");
    setErrorMessage(null);
    setProductId(null);

    setFile2(null);
    setPreview2(null);

    if (inputRef.current) inputRef.current.value = "";
    if (inputRef2.current) inputRef2.current.value = "";
  }, []);

  const handleDragStateChange = useCallback(
    (isDragging: boolean) => {
      if (uploadState === "idle" || uploadState === "dragging") {
        setUploadState(isDragging ? "dragging" : "idle");
      }
    },
    [uploadState]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      handleDragStateChange(false);
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile) handleFileSelect(droppedFile);
    },
    [handleFileSelect, handleDragStateChange]
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      handleDragStateChange(true);
    },
    [handleDragStateChange]
  );

  const handleDragLeave = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      handleDragStateChange(false);
    },
    [handleDragStateChange]
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFile = e.target.files?.[0];
      if (selectedFile) handleFileSelect(selectedFile);
    },
    [handleFileSelect]
  );

  const handleInputChange2 = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFile = e.target.files?.[0];
      if (selectedFile) handleSecondFileSelect(selectedFile);
    },
    [handleSecondFileSelect]
  );

  const handleBrowseClick = () => inputRef.current?.click();
  const handleBrowseClick2 = () => inputRef2.current?.click();

  const handleContinue = () => {
    if (!productId) return;
    window.location.href = "/presets";
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6 lg:px-8">
        <header className="mb-10 text-center">
          <h1 className="text-3xl font-semibold tracking-tight text-white">Upload your product</h1>
          <p className="mt-2 text-slate-400">Add 1–2 photos of your product (2nd is optional) to generate a consistent 5-pack.</p>
          <p className="mt-2 text-xs text-slate-500">API_BASE: {API_BASE}</p>
        </header>

        <div className="grid gap-6 lg:grid-cols-5">
          <section className="lg:col-span-3">
            <article className="overflow-hidden rounded-xl border border-white/10 bg-slate-900 shadow-[0_1px_0_0_rgba(255,255,255,0.04)]">
              {/* Primary uploader */}
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={!preview ? handleBrowseClick : undefined}
                onKeyDown={!preview ? (e) => e.key === "Enter" && handleBrowseClick() : undefined}
                className={`relative transition-all duration-200 ${uploadState === "dragging" ? "bg-white/5" : ""} ${
                  !preview ? "cursor-pointer hover:bg-white/5" : ""
                }`}
                role={!preview ? "button" : undefined}
                tabIndex={!preview ? 0 : undefined}
              >
                <input ref={inputRef} type="file" accept="image/*" onChange={handleInputChange} className="sr-only" />

                <div className="aspect-[4/3] w-full">
                  {preview ? (
                    <div className="relative h-full w-full">
                      <img src={preview} alt="Product preview" className="h-full w-full object-contain bg-black/30 p-4" />

                      {uploadState === "uploading" && (
                        <div className="absolute inset-0 flex items-center justify-center bg-slate-950/60 backdrop-blur-sm">
                          <div className="flex flex-col items-center gap-3">
                            <LoaderIcon className="size-8 animate-spin text-white" />
                            <span className="text-sm font-medium text-slate-200">Uploading...</span>
                          </div>
                        </div>
                      )}

                      {uploadState === "success" && (
                        <div className="absolute right-4 top-4">
                          <div className="flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-emerald-300">
                            <CheckCircle2Icon className="size-4" />
                            <span className="text-sm font-medium">Ready</span>
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div
                      className={`flex h-full flex-col items-center justify-center gap-4 border-2 border-dashed rounded-xl m-6 transition-colors ${
                        uploadState === "dragging" ? "border-sky-400 bg-sky-500/10" : "border-white/15 bg-black/10"
                      } ${uploadState === "error" ? "border-red-400/60" : ""}`}
                    >
                      <div
                        className={`rounded-full p-4 ring-1 ring-white/10 ${
                          uploadState === "dragging" ? "bg-sky-500/15 text-sky-300" : "bg-white/5 text-slate-300"
                        }`}
                      >
                        {uploadState === "dragging" ? <UploadCloudIcon className="size-8" /> : <ImageIcon className="size-8" />}
                      </div>
                      <div className="text-center">
                        <p className="text-sm font-medium text-white">{uploadState === "dragging" ? "Drop your image here" : "Drag and drop your product image"}</p>
                        <p className="mt-1 text-sm text-slate-400">
                          or <span className="font-medium text-white underline underline-offset-4">browse files</span>
                        </p>
                      </div>
                      <p className="text-xs text-slate-400/80">Supports JPG, PNG, WebP up to 10MB</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Inputs */}
              <div className="px-6 pb-6">
                <div className="grid gap-4">
                  <div>
                    <label className="block text-sm font-semibold text-white">Tipo de producto (opcional)</label>
                    <p className="mt-1 text-xs text-slate-400">Ej: “botella de vidrio”, “zapatillas deportivas”, “remera oversize”.</p>
                    <input
                      value={productType}
                      onChange={(e) => setProductType(e.target.value)}
                      placeholder='Ej: “zapatillas deportivas”'
                      className="mt-3 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-white/20"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-white">Preferencia estética</label>
                    <p className="mt-1 text-xs text-slate-400">Default: minimalista.</p>
                    <select
                      value={aesthetic}
                      onChange={(e) => setAesthetic(e.target.value)}
                      className="mt-3 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-white/20"
                    >
                      {["minimalista", "clean", "premium", "moderno", "luxury", "rustico"].map((x) => (
                        <option key={x} value={x}>
                          {x}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Optional 2nd image */}
                  <div className="rounded-xl border border-white/10 bg-black/10 p-4">
                    <div className="text-sm font-semibold text-white">2da foto (opcional)</div>
                    <div className="mt-1 text-xs text-slate-400">Útil para ropa (frente/espalda), botellas (etiqueta), zapatillas (suela), etc.</div>

                    <div className="mt-3 flex items-center gap-3">
                      <input ref={inputRef2} type="file" accept="image/*" onChange={handleInputChange2} className="hidden" />
                      <button
                        type="button"
                        onClick={handleBrowseClick2}
                        className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10"
                      >
                        <UploadCloudIcon className="size-4" />
                        Add second photo
                      </button>

                      {preview2 && (
                        <div className="flex items-center gap-2 text-xs text-slate-300">
                          <CheckCircle2Icon className="size-4 text-emerald-300" />
                          Second photo added
                        </div>
                      )}
                    </div>

                    {preview2 && (
                      <div className="mt-3 overflow-hidden rounded-lg border border-white/10 bg-black/20">
                        <img src={preview2} alt="Second preview" className="w-full max-h-64 object-contain" />
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {uploadState === "error" && errorMessage && (
                <div className="mx-6 mb-6 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-200">
                  <AlertCircleIcon className="size-4 shrink-0" />
                  <span className="text-sm">{errorMessage}</span>
                </div>
              )}

              {file && uploadState !== "error" && (
                <div className="border-t border-white/10 p-6">
                  <div className="flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="rounded-lg bg-white/5 p-2 ring-1 ring-white/10">
                        <FileIcon className="size-5 text-slate-300" />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-white">{file.name}</p>
                        <p className="text-xs text-slate-400">{formatFileSize(file.size)}</p>

                        {productId && (
                          <p className="mt-1 text-[11px] text-slate-400 truncate">
                            product_id: <span className="font-mono text-slate-200">{productId}</span>
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        onClick={handleRemove}
                        className="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-white/5 hover:text-red-200"
                      >
                        <XIcon className="size-4" />
                        <span>Remove</span>
                      </button>

                      <button
                        type="button"
                        onClick={handleContinue}
                        disabled={uploadState !== "success" || !productId}
                        className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Continue
                        <ArrowRightIcon className="size-4" />
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {!file && uploadState !== "error" && (
                <div className="border-t border-white/10 p-6">
                  <button
                    type="button"
                    onClick={handleBrowseClick}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-white/15 bg-white/5 px-4 py-2.5 text-sm font-semibold text-white hover:bg-white/10"
                  >
                    <UploadCloudIcon className="size-4" />
                    <span>Select Image</span>
                  </button>
                </div>
              )}
            </article>
          </section>

          <aside className="lg:col-span-2">
            <article className="h-fit rounded-xl border border-white/10 bg-slate-900 shadow-[0_1px_0_0_rgba(255,255,255,0.04)]">
              <header className="flex items-center justify-between border-b border-white/10 p-5">
                <h2 className="flex items-center gap-2 text-base font-semibold text-white">
                  <LightbulbIcon className="size-4 text-amber-300" />
                  Tips for best results
                </h2>
                <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-medium text-slate-200">
                  Step {currentStep} of {totalSteps}
                </span>
              </header>

              <div className="p-5">
                <ul className="space-y-4" role="list">
                  {tips.map((tip, index) => (
                    <li key={index} className="flex gap-3">
                      <div className="shrink-0 rounded-lg bg-white/5 p-2 ring-1 ring-white/10">
                        <tip.icon className="size-4 text-slate-300" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-white">{tip.title}</p>
                        <p className="text-sm text-slate-400">{tip.description}</p>
                      </div>
                    </li>
                  ))}
                </ul>

                <div className="mt-6 border-t border-white/10 pt-6">
                  <div className="mb-2 flex items-center justify-between text-sm text-slate-400">
                    <span>Progress</span>
                    <span>{Math.round((currentStep / totalSteps) * 100)}%</span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
                    <div className="h-full rounded-full bg-white transition-all duration-500 ease-out" style={{ width: `${(currentStep / totalSteps) * 100}%` }} />
                  </div>

                  <div className="mt-4 flex items-center gap-2">
                    {Array.from({ length: totalSteps }, (_, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <div
                          className={`flex size-6 items-center justify-center rounded-full text-xs font-medium ${
                            i + 1 <= currentStep ? "bg-white text-slate-950" : "bg-white/10 text-slate-400"
                          }`}
                        >
                          {i + 1 < currentStep ? <CheckIcon className="size-3" /> : i + 1}
                        </div>
                        {i < totalSteps - 1 && <div className={`h-px w-6 ${i + 1 < currentStep ? "bg-white" : "bg-white/15"}`} />}
                      </div>
                    ))}
                  </div>

                  <div className="mt-3 flex justify-between text-xs text-slate-400">
                    <span>Upload</span>
                    <span>Style</span>
                    <span>Generate</span>
                  </div>
                </div>
              </div>
            </article>
          </aside>
        </div>
      </div>
    </main>
  );
}
