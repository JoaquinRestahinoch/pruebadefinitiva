"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE = "http://127.0.0.1:8000";

type Options = {
  environment_types: string[];
  scenes_by_type: Record<string, string[]>;
  chips: string[];
  styles: string[];
  lightings: string[];
  model: {
    genders: string[];
    age_ranges: string[];
  };
};

export default function PresetsPage() {
  const router = useRouter();

  const [productId, setProductId] = useState<string | null>(null);

  const [options, setOptions] = useState<Options | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  // Config state
  const [envType, setEnvType] = useState<string>("studio");
  const [scene, setScene] = useState<string>("white");
  const [chips, setChips] = useState<string[]>([]);
  const [customText, setCustomText] = useState<string>("");

  const [style, setStyle] = useState<string>("ecommerce");
  const [lighting, setLighting] = useState<string>("studio_soft");

  const [modelEnabled, setModelEnabled] = useState(false);
  const [modelGender, setModelGender] = useState<string>("female");
  const [modelAge, setModelAge] = useState<string>("25-35");
  const [modelAppearance, setModelAppearance] = useState<string>("");

  useEffect(() => {
    const pid = localStorage.getItem("product_id");
    setProductId(pid);
  }, []);

  useEffect(() => {
    async function loadOptions() {
      try {
        setLoading(true);
        setErr(null);

        const res = await fetch(`${API_BASE}/options`);
        const data = await res.json();
        if (!res.ok) throw new Error(data?.detail || "No pude cargar options");

        setOptions(data);

        // Defaults coherentes según options
        const defaultEnv = data.environment_types?.[0] || "studio";
        setEnvType(defaultEnv);
        const firstScene = data.scenes_by_type?.[defaultEnv]?.[0] || "white";
        setScene(firstScene);

        setStyle(data.styles?.[0] || "ecommerce");
        setLighting(data.lightings?.[0] || "studio_soft");
      } catch (e: any) {
        setErr(e?.message || "Error");
      } finally {
        setLoading(false);
      }
    }

    loadOptions();
  }, []);

  // Cuando cambia envType, elegimos primera escena válida
  useEffect(() => {
    if (!options) return;
    const scenes = options.scenes_by_type?.[envType] || [];
    setScene(scenes[0] || "");
    setChips([]);
  }, [envType, options]);

  const toggleChip = (c: string) => {
    setChips((prev) =>
      prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]
    );
  };

  const handleContinue = () => {
    if (!productId) return;

    const payload = {
      product_id: productId,
      environment: {
        type: envType,
        scene,
        chips,
        custom_text: customText,
      },
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
      <main className="min-h-screen flex items-center justify-center bg-slate-950 text-white px-4">
        <div className="w-full max-w-md rounded-2xl border border-white/10 bg-slate-900 p-8 shadow-[0_1px_0_0_rgba(255,255,255,0.04)]">
          <h1 className="text-xl font-semibold mb-2 text-white">
            No hay product_id
          </h1>
          <p className="text-slate-300 text-sm">
            Volvé a{" "}
            <a className="underline underline-offset-4 text-white" href="/upload">
              /upload
            </a>{" "}
            y subí una imagen.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto max-w-4xl px-4 py-10">
        <div className="rounded-2xl border border-white/10 bg-slate-900 p-8 shadow-[0_1px_0_0_rgba(255,255,255,0.04)]">
          <h1 className="text-2xl font-semibold text-white">Elegí el estilo</h1>
          <p className="text-slate-300 text-sm mt-2">
            Producto: <span className="font-mono text-slate-200">{productId}</span>
          </p>

          {loading && (
            <p className="mt-6 text-sm text-slate-300">Cargando opciones...</p>
          )}
          {err && (
            <p className="mt-6 text-sm text-red-200">
              ❌ {err}
            </p>
          )}

          {!loading && options && (
            <div className="mt-8 grid gap-6">
              {/* ENV */}
              <div className="grid gap-2">
                <label className="text-sm font-medium text-white">
                  Tipo de entorno
                </label>
                <select
                  className="border border-white/15 bg-white/5 text-white rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-sky-400/40 focus:border-sky-400/40"
                  value={envType}
                  onChange={(e) => setEnvType(e.target.value)}
                >
                  {options.environment_types.map((t) => (
                    <option key={t} value={t} className="bg-slate-900">
                      {t}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid gap-2">
                <label className="text-sm font-medium text-white">
                  Escena / fondo
                </label>
                <select
                  className="border border-white/15 bg-white/5 text-white rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-sky-400/40 focus:border-sky-400/40"
                  value={scene}
                  onChange={(e) => setScene(e.target.value)}
                >
                  {(options.scenes_by_type[envType] || []).map((s) => (
                    <option key={s} value={s} className="bg-slate-900">
                      {s}
                    </option>
                  ))}
                </select>
              </div>

              {/* CHIPS */}
              <div className="grid gap-2">
                <label className="text-sm font-medium text-white">
                  Mood (chips)
                </label>
                <div className="flex flex-wrap gap-2">
                  {options.chips.map((c) => {
                    const active = chips.includes(c);
                    return (
                      <button
                        key={c}
                        type="button"
                        onClick={() => toggleChip(c)}
                        className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                          active
                            ? "bg-white text-slate-950 border-white"
                            : "bg-white/5 text-slate-200 border-white/15 hover:bg-white/10"
                        }`}
                      >
                        {c}
                      </button>
                    );
                  })}
                </div>
                <p className="text-xs text-slate-400">
                  Tip: no te pases con chips. 1-3 suele andar mejor.
                </p>
              </div>

              {/* Extra */}
              <div className="grid gap-2">
                <label className="text-sm font-medium text-white">
                  Detalles extra (opcional)
                </label>
                <input
                  className="border border-white/15 bg-white/5 text-white placeholder:text-slate-400 rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-sky-400/40 focus:border-sky-400/40"
                  value={customText}
                  onChange={(e) => setCustomText(e.target.value)}
                  placeholder="Ej: mármol blanco, reflejos suaves, estética joyería"
                />
              </div>

              {/* STYLE/LIGHT */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <label className="text-sm font-medium text-white">
                    Estilo fotográfico
                  </label>
                  <select
                    className="border border-white/15 bg-white/5 text-white rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-sky-400/40 focus:border-sky-400/40"
                    value={style}
                    onChange={(e) => setStyle(e.target.value)}
                  >
                    {options.styles.map((s) => (
                      <option key={s} value={s} className="bg-slate-900">
                        {s}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="grid gap-2">
                  <label className="text-sm font-medium text-white">
                    Iluminación
                  </label>
                  <select
                    className="border border-white/15 bg-white/5 text-white rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-sky-400/40 focus:border-sky-400/40"
                    value={lighting}
                    onChange={(e) => setLighting(e.target.value)}
                  >
                    {options.lightings.map((l) => (
                      <option key={l} value={l} className="bg-slate-900">
                        {l}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* MODEL */}
              <div className="border border-white/10 bg-black/10 rounded-2xl p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-white">
                      Modelo / persona
                    </div>
                    <div className="text-xs text-slate-400">
                      Útil para joyería, ropa, cosmética. (Riesgo: tape producto)
                    </div>
                  </div>
                  <label className="flex items-center gap-2 text-sm text-slate-200">
                    <input
                      type="checkbox"
                      checked={modelEnabled}
                      onChange={(e) => setModelEnabled(e.target.checked)}
                      className="h-4 w-4 accent-white"
                    />
                    Activar
                  </label>
                </div>

                {modelEnabled && (
                  <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="grid gap-2">
                      <label className="text-sm font-medium text-white">
                        Género
                      </label>
                      <select
                        className="border border-white/15 bg-white/5 text-white rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-sky-400/40 focus:border-sky-400/40"
                        value={modelGender}
                        onChange={(e) => setModelGender(e.target.value)}
                      >
                        {options.model.genders.map((g) => (
                          <option key={g} value={g} className="bg-slate-900">
                            {g}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="grid gap-2">
                      <label className="text-sm font-medium text-white">
                        Edad
                      </label>
                      <select
                        className="border border-white/15 bg-white/5 text-white rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-sky-400/40 focus:border-sky-400/40"
                        value={modelAge}
                        onChange={(e) => setModelAge(e.target.value)}
                      >
                        {options.model.age_ranges.map((a) => (
                          <option key={a} value={a} className="bg-slate-900">
                            {a}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="sm:col-span-2 grid gap-2">
                      <label className="text-sm font-medium text-white">
                        Apariencia (opcional)
                      </label>
                      <input
                        className="border border-white/15 bg-white/5 text-white placeholder:text-slate-400 rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-sky-400/40 focus:border-sky-400/40"
                        value={modelAppearance}
                        onChange={(e) => setModelAppearance(e.target.value)}
                        placeholder="Ej: look elegante, manos con manicure prolija, etc."
                      />
                    </div>
                  </div>
                )}
              </div>

              <button
                onClick={handleContinue}
                className="w-full rounded-xl bg-white py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-white/90"
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
