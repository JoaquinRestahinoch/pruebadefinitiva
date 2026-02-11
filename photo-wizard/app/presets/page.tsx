"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

type Options = {
  environment_types: string[];
  scenes_by_type: Record<string, string[]>;
  chips: string[];
  styles: string[];
  lightings: string[];
  model: { genders: string[]; age_ranges: string[] };
};

function buildAutoDetails(meta: any): string {
  const prefill = (meta?.prefill_custom_text || "").trim();

  const auto = meta?.auto_product_desc || {};
  const descLong = (auto?.product_description_long || "").trim();
  const titleShort = (auto?.title_short || "").trim();
  const category = (auto?.category_guess || "").trim();

  const features: string[] = Array.isArray(auto?.key_visual_features) ? auto.key_visual_features : [];
  const materials: string[] = Array.isArray(auto?.materials) ? auto.materials : [];
  const colors: string[] = Array.isArray(auto?.colors) ? auto.colors : [];
  const textures: string[] = Array.isArray(auto?.finish_texture) ? auto.finish_texture : [];
  const boosters: string[] = Array.isArray(auto?.prompt_boosters) ? auto.prompt_boosters : [];

  const hasCore = !!descLong || boosters.length > 0;

  const lines: string[] = [];

  // Si la auto-descripción falló, no rompemos nada: caemos al prefill clásico.
  if (hasCore) {
    lines.push("DESCRIPCIÓN DEL PRODUCTO (auto, SOLO para preservar detalles):");
    if (titleShort) lines.push(`- Título: ${titleShort}`);
    if (category) lines.push(`- Categoría: ${category}`);
    if (descLong) lines.push(`- Descripción: ${descLong}`);

    if (colors.length) lines.push(`- Colores visibles: ${colors.join(", ")}`);
    if (materials.length) lines.push(`- Materiales probables: ${materials.join(", ")}`);
    if (textures.length) lines.push(`- Acabado/textura: ${textures.join(", ")}`);

    if (features.length) {
      lines.push("- Rasgos visuales clave:");
      features.slice(0, 10).forEach((f) => lines.push(`  • ${String(f)}`));
    }

    if (boosters.length) {
      lines.push("BOOSTERS (para mejorar realismo y lock):");
      boosters.slice(0, 12).forEach((b) => lines.push(`- ${String(b)}`));
    }

    lines.push(""); // separador
  }

  if (prefill) {
    lines.push("REGLAS RECOMENDADAS (por tipo/estética):");
    lines.push(prefill);
  }

  return lines.join("\n").trim();
}

export default function PresetsPage() {
  const router = useRouter();
  const [productId, setProductId] = useState<string | null>(null);

  const [options, setOptions] = useState<Options | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  // Config
  const [envType, setEnvType] = useState<string>("studio");
  const [scene, setScene] = useState<string>("white");
  const [sceneText, setSceneText] = useState<string>(""); // ✅ NUEVO
  const [chips, setChips] = useState<string[]>([]);
  const [customText, setCustomText] = useState<string>("");

  const [backgroundRefId, setBackgroundRefId] = useState<string | null>(null);
  const [backgroundUploading, setBackgroundUploading] = useState(false);
  const [backgroundError, setBackgroundError] = useState<string | null>(null);

  const [style, setStyle] = useState<string>("ecommerce");
  const [lighting, setLighting] = useState<string>("studio_soft");

  const [modelEnabled, setModelEnabled] = useState(false);
  const [modelGender, setModelGender] = useState<string>("female");
  const [modelAge, setModelAge] = useState<string>("25-35");
  const [modelAppearance, setModelAppearance] = useState<string>("");

  const [didPrefill, setDidPrefill] = useState(false);

  useEffect(() => {
    setProductId(localStorage.getItem("product_id"));
  }, []);

  useEffect(() => {
    async function loadAll() {
      try {
        setLoading(true);
        setErr(null);

        if (!productId) {
          setLoading(false);
          return;
        }

        // 1) options
        const optRes = await fetch(`${API_BASE}/options`);
        const optData = await optRes.json().catch(() => null);
        if (!optRes.ok) throw new Error(optData?.detail || "No pude cargar options");
        setOptions(optData);

        // defaults fallback
        const fallbackEnv = optData.environment_types?.[0] || "studio";
        const fallbackScene = optData.scenes_by_type?.[fallbackEnv]?.[0] || "white";

        // 2) meta: auto desc + prefill + recommended_config
        const metaRes = await fetch(`${API_BASE}/product-meta/${productId}`);
        const metaData = await metaRes.json().catch(() => null);

        if (metaRes.ok && metaData?.meta && !didPrefill) {
          const meta = metaData.meta;
          const reco = meta.recommended_config || {};

          // recommended defaults
          const rEnvType = reco?.environment?.type || fallbackEnv;
          const rScene = reco?.environment?.scene || fallbackScene;
          const rChips = Array.isArray(reco?.environment?.chips) ? reco.environment.chips : [];
          const rStyle = reco?.style || (optData.styles?.[0] || "ecommerce");
          const rLighting = reco?.lighting || (optData.lightings?.[0] || "studio_soft");

          setEnvType(rEnvType);
          setScene(rScene);
          setChips(rChips);
          setStyle(rStyle);
          setLighting(rLighting);

          // 🔥 NUEVO: Detalles extra ahora combina auto-descripción + boosters + prefill.
          // Solo lo seteamos si el user no escribió nada.
          if (!customText.trim()) {
            const autoDetails = buildAutoDetails(meta);
            if (autoDetails) setCustomText(autoDetails);
          }

          setDidPrefill(true);
        } else {
          // si no hay meta/reco, caemos a defaults simples
          setEnvType(fallbackEnv);
          setScene(fallbackScene);
          setStyle(optData.styles?.[0] || "ecommerce");
          setLighting(optData.lightings?.[0] || "studio_soft");
        }
      } catch (e: any) {
        setErr(e?.message || "Error");
      } finally {
        setLoading(false);
      }
    }

    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productId]);

  // si el user cambia envType manualmente, ajustamos escena si la actual no es válida
  useEffect(() => {
  if (!options) return;
  // ✅ Si hay escena libre, NO tocamos envType/scene (porque no se usan)
  if (sceneText.trim()) return;

  const scenes = options.scenes_by_type?.[envType] || [];
  if (!scenes.includes(scene)) setScene(scenes[0] || "");
}, [envType, options, sceneText]); // ✅ sumá sceneText


  const toggleChip = (c: string) => {
    setChips((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  };

  async function uploadBackgroundRef(file: File) {
    setBackgroundUploading(true);
    setBackgroundError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);

      const res = await fetch(`${API_BASE}/upload-background-ref`, {
        method: "POST",
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Upload background failed");

      setBackgroundRefId(data.background_ref_id);
    } catch (e: any) {
      setBackgroundError(e?.message || "Error uploading background");
    } finally {
      setBackgroundUploading(false);
    }
  }

  const handleContinue = () => {
    if (!productId) return;

    const payload = {
      product_id: productId,
      environment: { type: envType, scene, scene_text: sceneText, chips, custom_text: customText },
      background_ref_id: backgroundRefId,
      style,
      lighting,
      model: {
        enabled: modelEnabled,
        gender: modelEnabled ? modelGender : null,
        age_range: modelEnabled ? modelAge : null,
        appearance: modelEnabled ? modelAppearance : "",
      },
    };

    localStorage.setItem("gen_config", JSON.stringify(payload));
    router.push("/generate");
  };

  if (!productId) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-slate-950 text-white">
        <div className="bg-slate-900 p-8 rounded-2xl border border-white/10 w-full max-w-md">
          <h1 className="text-xl font-semibold mb-2">No hay product_id</h1>
          <p className="text-slate-300 text-sm">
            Volvé a <a className="underline" href="/upload">/upload</a> y subí una imagen.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto max-w-4xl px-4 py-10">
        <div className="bg-slate-900 rounded-2xl border border-white/10 p-8">
          <h1 className="text-2xl font-semibold">Elegí el estilo</h1>
          <p className="text-slate-300 text-sm mt-2">
            Producto: <span className="font-mono">{productId}</span>
          </p>

          {loading && <p className="mt-6 text-sm text-slate-300">Cargando…</p>}
          {err && <p className="mt-6 text-sm text-red-300">❌ {err}</p>}

          {!loading && options && (
            <div className="mt-8 grid gap-6">
              <div className="grid gap-2">
                <label className="text-sm font-medium text-white">Fondo de referencia (opcional)</label>
                <p className="text-xs text-slate-400">
                  Si subís una foto de fondo/set, se desactivan los presets de escena para que no se pise.
                </p>
                <input
                  type="file"
                  accept="image/*"
                  className="mt-2 block w-full text-sm text-slate-300 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-semibold file:bg-white/10 file:text-white hover:file:bg-white/20"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) uploadBackgroundRef(f);
                  }}
                />
                {backgroundUploading && <div className="mt-2 text-xs text-slate-400">Subiendo fondo…</div>}
                {backgroundError && <div className="mt-2 text-xs text-red-300">{backgroundError}</div>}
                {backgroundRefId && (
                  <div className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs text-emerald-200">
                    Background reference ON ✅ (presets de escena deshabilitados)
                  </div>
                )}
                {backgroundRefId && (
                  <button
                    type="button"
                    className="mt-3 w-full rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-xs font-semibold hover:bg-white/10"
                    onClick={() => setBackgroundRefId(null)}
                  >
                    Quitar fondo de referencia
                  </button>
                )}
              </div>

              <div className="grid gap-2">
                <label className="text-sm font-medium text-white">Escenario (texto libre)</label>
                <p className="text-xs text-slate-400">
                  Ej: "playa al atardecer", "cancha de básquet indoor", "barbería vintage", "joyería en la playa".
                  Si completás esto, se ignoran los selects de entorno/escena.
                </p>
                <input
                  className="border border-white/10 bg-black/20 text-white rounded-xl px-3 py-2 placeholder:text-slate-500"
                  value={sceneText}
                  onChange={(e) => setSceneText(e.target.value)}
                  placeholder='Ej: "playa al atardecer"'
                />
                <p className="text-xs text-emerald-300">
                  {sceneText.trim() ? "✅ Escenario libre activo (se ignoran los presets)" : backgroundRefId ? "✅ Usando fondo de referencia (presets deshabilitados)" : "⚪ Vacío: se usan presets de entorno/escena"}
                </p>
              </div>

              {!sceneText.trim() && !backgroundRefId ? (
                <>
                  <div className="grid gap-2">
                    <label className="text-sm font-medium text-white">Tipo de entorno</label>
                    <select
                      className="border border-white/10 bg-black/20 text-white rounded-xl px-3 py-2"
                      value={envType}
                      onChange={(e) => setEnvType(e.target.value)}
                    >
                      {options.environment_types.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>

                  <div className="grid gap-2">
                    <label className="text-sm font-medium text-white">Escena / fondo</label>
                    <select
                      className="border border-white/10 bg-black/20 text-white rounded-xl px-3 py-2"
                      value={scene}
                      onChange={(e) => setScene(e.target.value)}
                    >
                      {(options.scenes_by_type[envType] || []).map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </div>
                </>
              ) : (
                <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-slate-300">
                  {sceneText.trim() && "Presets de escena desactivados: estás usando escenario libre"}
                  {backgroundRefId && "Presets de escena desactivados: estás usando fondo de referencia"}
                </div>
              )}

              <div className="grid gap-2">
                <label className="text-sm font-medium text-white">Mood (chips)</label>
                <div className="flex flex-wrap gap-2">
                  {options.chips.map((c) => {
                    const active = chips.includes(c);
                    return (
                      <button
                        key={c}
                        type="button"
                        onClick={() => toggleChip(c)}
                        className={`px-3 py-1.5 rounded-full text-sm border ${
                          active
                            ? "bg-white text-slate-950 border-white"
                            : "bg-black/20 text-white border-white/10 hover:border-white/20"
                        }`}
                      >
                        {c}
                      </button>
                    );
                  })}
                </div>
                <p className="text-xs text-slate-400">Tip: 1-3 chips suele andar mejor.</p>
              </div>

              <div className="grid gap-2">
                <label className="text-sm font-medium text-white">Detalles extra (auto: descripción + boosters + reglas)</label>
                <textarea
                  className="border border-white/10 bg-black/20 text-white rounded-xl px-3 py-2 placeholder:text-slate-500 min-h-[160px]"
                  value={customText}
                  onChange={(e) => setCustomText(e.target.value)}
                  placeholder="Se autocompleta desde meta (auto-descripción + boosters + recomendaciones). Podés editarlo."
                />
                <p className="text-xs text-emerald-300">
                  {customText.trim() ? "✅ Visible y editable" : "⚠️ Vacío: revisá product-meta/auto_product_desc y prefill_custom_text"}
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <label className="text-sm font-medium text-white">Estilo</label>
                  <select
                    className="border border-white/10 bg-black/20 text-white rounded-xl px-3 py-2"
                    value={style}
                    onChange={(e) => setStyle(e.target.value)}
                  >
                    {options.styles.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>

                <div className="grid gap-2">
                  <label className="text-sm font-medium text-white">Iluminación</label>
                  <select
                    className="border border-white/10 bg-black/20 text-white rounded-xl px-3 py-2"
                    value={lighting}
                    onChange={(e) => setLighting(e.target.value)}
                  >
                    {options.lightings.map((l) => (
                      <option key={l} value={l}>{l}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="border border-white/10 rounded-2xl p-4 bg-black/20">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-white">Modelo / persona</div>
                    <div className="text-xs text-slate-400">
                      Recomendación: activarlo solo si el producto lo pide (ropa/joyería).
                    </div>
                  </div>
                  <label className="flex items-center gap-2 text-sm text-slate-200">
                    <input
                      type="checkbox"
                      checked={modelEnabled}
                      onChange={(e) => setModelEnabled(e.target.checked)}
                    />
                    Activar
                  </label>
                </div>

                {modelEnabled && (
                  <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="grid gap-2">
                      <label className="text-sm font-medium text-white">Género</label>
                      <select
                        className="border border-white/10 bg-black/20 text-white rounded-xl px-3 py-2"
                        value={modelGender}
                        onChange={(e) => setModelGender(e.target.value)}
                      >
                        {options.model.genders.map((g) => (
                          <option key={g} value={g}>{g}</option>
                        ))}
                      </select>
                    </div>

                    <div className="grid gap-2">
                      <label className="text-sm font-medium text-white">Edad</label>
                      <select
                        className="border border-white/10 bg-black/20 text-white rounded-xl px-3 py-2"
                        value={modelAge}
                        onChange={(e) => setModelAge(e.target.value)}
                      >
                        {options.model.age_ranges.map((a) => (
                          <option key={a} value={a}>{a}</option>
                        ))}
                      </select>
                    </div>

                    <div className="sm:col-span-2 grid gap-2">
                      <label className="text-sm font-medium text-white">Apariencia</label>
                      <input
                        className="border border-white/10 bg-black/20 text-white rounded-xl px-3 py-2 placeholder:text-slate-500"
                        value={modelAppearance}
                        onChange={(e) => setModelAppearance(e.target.value)}
                        placeholder="Ej: look elegante, manos prolijas, etc."
                      />
                    </div>
                  </div>
                )}
              </div>

              <button
                onClick={handleContinue}
                className="w-full bg-white text-slate-950 py-3 rounded-xl font-semibold hover:bg-white/90"
              >
                Continuar a generar →
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
