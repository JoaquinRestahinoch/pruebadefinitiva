"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function uploadProduct() {
    if (!file) return;

    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${API_BASE}/upload-product`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Error subiendo imagen");
      }

      localStorage.setItem("product_id", data.product_id);
      window.location.href = "/presets";
    } catch (e: any) {
      setError(e.message || "Error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-slate-100">
      <div className="bg-white p-8 rounded-2xl shadow-md w-full max-w-md">
        <h1 className="text-xl font-semibold mb-4">
          Subí la foto del producto
        </h1>

        <input
          type="file"
          accept="image/*"
          onChange={(e) => {
  const f = e.target.files?.[0] ?? null;
  setFile(f);
  alert(f ? `Archivo: ${f.name}` : "No agarró archivo");
}}

          className="w-full mb-4 text-sm"
        />

        <button
          onClick={uploadProduct}
          disabled={!file || loading}
          className="w-full bg-black text-white py-2 rounded-xl disabled:opacity-50"
        >
          {loading ? "Subiendo..." : "Continuar"}
        </button>

        {error && (
          <div className="mt-4 text-red-600 text-sm">❌ {error}</div>
        )}
      </div>
    </main>
  );
}
