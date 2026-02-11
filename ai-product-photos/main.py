import os
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Literal, Dict, Any, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from google import genai
from google.genai import types

load_dotenv()

app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_BASE = os.getenv("API_BASE") or "http://127.0.0.1:8000"

# --- Folders ---
OUTPUT_DIR = Path("outputs"); OUTPUT_DIR.mkdir(exist_ok=True)
PRODUCTS_DIR = Path("products"); PRODUCTS_DIR.mkdir(exist_ok=True)
PRODUCTS_META_DIR = Path("products_meta"); PRODUCTS_META_DIR.mkdir(exist_ok=True)
BACKGROUNDS_DIR = Path("backgrounds"); BACKGROUNDS_DIR.mkdir(exist_ok=True)

# --- Presets clásicos (opcionales) ---
PRESETS = {
    "catalogo_blanco": {
        "title": "Catálogo fondo blanco",
        "prompt": "Fondo blanco puro, sombra suave, iluminación de estudio, producto centrado.",
    },
    "catalogo_gris": {
        "title": "Catálogo fondo gris",
        "prompt": "Fondo gris claro uniforme, iluminación suave de estudio.",
    },
    "lifestyle_cocina": {
        "title": "Lifestyle cocina",
        "prompt": "Cocina moderna minimalista, luz natural, sin personas.",
    },
    "instagram_ads": {
        "title": "Instagram Ads",
        "prompt": "Foto publicitaria moderna para redes sociales.",
    },
}

# ===================== SISTEMA CONFIGURABLE =====================

EnvironmentType = Literal["studio", "indoor_real", "lifestyle", "outdoor"]
LightingType = Literal["studio_soft", "natural", "premium", "dramatic"]
StyleType = Literal["ecommerce", "lifestyle", "advertising", "instagram_ads"]
ChipType = Literal["luxury", "minimal", "modern", "rustic", "clean", "premium"]

class EnvironmentConfig(BaseModel):
    type: EnvironmentType
    scene: str
    scene_text: Optional[str] = ""
    chips: List[ChipType] = []
    custom_text: Optional[str] = ""

class ModelConfig(BaseModel):
    enabled: bool = False
    gender: Optional[Literal["female", "male"]] = None
    age_range: Optional[Literal["baby","10-18","18-24", "25-35", "36-50", "50+"]] = None
    appearance: Optional[str] = ""

class GeneratePresetRequest(BaseModel):
    product_id: str
    preset: str

class GenerateFromProductConfigRequest(BaseModel):
    product_id: str
    environment: EnvironmentConfig
    style: StyleType = "ecommerce"
    lighting: LightingType = "studio_soft"
    model: ModelConfig = ModelConfig(enabled=False)
    background_ref_id: Optional[str] = None

class GeneratePackRequest(BaseModel):
    product_id: str
    environment: EnvironmentConfig
    style: StyleType = "ecommerce"
    lighting: LightingType = "studio_soft"
    model: ModelConfig = ModelConfig(enabled=False)
    n: int = 5
    background_ref_id: Optional[str] = None

# --- Options para el front ---
SCENES_BY_TYPE = {
    "studio": {"white", "gray", "black", "gradient", "textured"},
    "indoor_real": {"kitchen", "bathroom", "living_room", "jewelry_store", "office"},
    "lifestyle": {"cafe", "home", "desk", "gym", "street"},
    "outdoor": {"urban", "nature", "beach", "city_night"},
}

CHIPS = ["luxury", "minimal", "modern", "rustic", "clean", "premium"]
STYLES = ["ecommerce", "lifestyle", "advertising", "instagram_ads"]
LIGHTINGS = ["studio_soft", "natural", "premium", "dramatic"]

# ===================== PROMPTS “PRODUCT-GRADE” =====================

LOCK_PRODUCT_CLAUSE = """
Producto locked (OBLIGATORIO):
- El producto debe quedar IDENTICO al original en lo que ES real: forma, proporciones, textura, costuras visibles, etiquetas visibles, logos y tipografías existentes, colores exactos.
- NO inventes partes, NO borres detalles, NO deformes bordes, NO cambies materiales.
- No “mejores” el producto: solo cambia entorno, luz, composición y (si aplica) convertir mockup a prenda real sin cambiar el diseño.
"""

NO_TEXT_CLAUSE = """
Restricciones (OBLIGATORIO):
- NO agregues texto nuevo, NO agregues logos nuevos, NO agregues marcas de agua.
- NO agregues packaging inventado si no está en la foto.
- NO agregues manos/personas salvo que se habilite explícitamente modelo/persona.
"""

HYPERREALISM_CLAUSE = """
Hiperrealismo fotográfico (OBLIGATORIO):
- Debe parecer 100% una FOTO REAL (no CGI, no render, no ilustración).
- Iluminación físicamente plausible, sombras coherentes y realistas, sin halos alrededor del producto.
- Texturas naturales y nítidas (sin plasticidad rara, sin patrones falsos).
- Color fiel al original (balance de blancos correcto, sin shifts).
- Sin artefactos: sin bordes derretidos, sin banding, sin ruido extraño, sin duplicaciones.
- Nitidez comercial tipo e-commerce, micro-contraste sutil, look de estudio real.
"""

CONSISTENCY_CLAUSE = """
Consistencia de shoot (OBLIGATORIO):
- Mantener estilo/iluminación coherentes con el setting elegido (como un mismo set fotográfico).
- Fondo limpio y controlado; no exagerar efectos cinematográficos.
"""

MULTIVIEW_CLAUSE = """
REFERENCIAS DEL PRODUCTO (OBLIGATORIO):
- Imagen 1 = vista principal del producto (frente / vista general).
- Imagen 2 = vista secundaria del MISMO producto (ej: espalda / etiqueta / otro ángulo).
- Ambas imágenes son el MISMO ítem (no variantes). Deben coincidir: forma, colores, costuras, tipografías, materiales, etiquetas reales.
- Usá Imagen 2 para corregir detalles que Imagen 1 no muestre. NO inventes nada que no esté en ninguna de las dos.
"""

# ✅ clave para tu caso
DEMOCKUP_CLAUSE = """
INPUT MOCKUP → CONVERSIÓN A PRENDA REAL (OBLIGATORIO - PRIORIDAD MÁXIMA PARA APPAREL):

La imagen de entrada puede ser un MOCKUP digital (PNG/plano/silueta perfecta).
Debés convertirlo en una PRENDA REAL FOTOGRAFIADA.

REGLAS:
- Mantener EXACTAMENTE el diseño gráfico: mismo logo, mismo texto, mismo layout/ubicación y mismo tamaño relativo.
- Mantener EXACTO el color base y los colores del print.
- Convertir el soporte a prenda real: tela con textura visible, micro-arrugas naturales, caída real, costuras reales, bordes naturales (NO recorte perfecto).
- Eliminar look mockup: bordes demasiado perfectos, sombra pintada, iluminación plana, silueta rígida.
- Agregar gravedad real: volumen y peso realistas.
- Debe verse como FOTO DE E-COMMERCE REAL, no como diseño pegado a una silueta.
"""

BACKGROUND_REF_LOCK_CLAUSE = """
REFERENCIA DE FONDO/SET (OBLIGATORIO - PRIORIDAD MÁXIMA SI HAY IMAGEN DE REFERENCIA):
- Te doy una imagen de referencia del fondo/set (background reference).
- Debés replicar ese set lo MÁS EXACTO posible: tipo de lugar, superficie, paleta, props, dirección de luz, atmósfera y hora del día.
- PROHIBIDO: cambiar la locación por otra (ej: playa → gimnasio).
- Solo puede variar: ángulo de cámara, encuadre, foco (DOF) y posición/rotación del producto.
"""

MODEL_IDENTITY_LOCK_CLAUSE = """
CONSISTENCIA DE MODELO (OBLIGATORIO - PRIORIDAD MÁXIMA SI HAY MODELO):
- Debe ser EXACTAMENTE la misma persona en TODAS las fotos: mismo rostro, facciones, tono de piel, nariz, labios, mandíbula, cejas, ojos, orejas.
- Mantener también: mismo peinado/longitud/color de pelo, mismo estilo de maquillaje (si hay), misma complexión corporal.
- PROHIBIDO: cambiar edad aparente, cambiar etnia aparente, cambiar forma de cara, “beautify”, cambiar pelo, agregar/quitar barba, cambiar cejas.
- Variaciones permitidas: micro-expresión natural + leve cambio de pose, pero identidad idéntica.
- Si no podés mantener la identidad 100%, preferí NO mostrar la cara (crop / perfil parcial / espalda) antes que inventar otra persona.
"""

EXTRA_REFS_CLAUSE = """
REFERENCIAS EXTRA (DETALLES) (OBLIGATORIO SI EXISTEN):
- Además de Imagen 1 y 2, te puedo pasar imágenes extra etiquetadas (ej: "bordado", "estampa", "cuello", "etiqueta", "parte trasera").
- Sirven SOLO para lockear microdetalles del MISMO producto (texturas, costuras, patrón del bordado/estampa).
- NO cambian el escenario/fondo.
- PROHIBIDO copiar el "mockup look": convertir a prenda real hiperrealista (tela real, caída, volumen natural).
- Si algún detalle no se ve claro, NO inventes: mantenelo neutro.
"""

# ===================== HELPERS =====================

def _client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY no configurada")
    return genai.Client(api_key=api_key)

def _find_product_path(product_id: str) -> Path:
    for ext in ["png", "jpg", "jpeg", "webp"]:
        p = PRODUCTS_DIR / f"{product_id}.{ext}"
        if p.exists():
            return p
    raise HTTPException(status_code=404, detail="Producto no encontrado")

def _find_secondary_path(product_id: str) -> Optional[Path]:
    for ext in ["png", "jpg", "jpeg", "webp"]:
        p = PRODUCTS_DIR / f"{product_id}_2.{ext}"
        if p.exists():
            return p
    return None

def _find_bgref_path(product_id: str) -> Optional[Path]:
    for ext in ["png", "jpg", "jpeg", "webp"]:
        p = PRODUCTS_DIR / f"{product_id}_bg.{ext}"
        if p.exists():
            return p
    return None

def _mime_for_path(p: Path) -> str:
    ext = p.suffix.lower().replace(".", "")
    return "image/jpeg" if ext in ["jpg", "jpeg"] else f"image/{ext}"

def _secondary_bytes(product_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    p2 = _find_secondary_path(product_id)
    if not p2:
        return None, None
    try:
        b = p2.read_bytes()
        if not b:
            return None, None
        return b, _mime_for_path(p2)
    except Exception:
        return None, None

def _bgref_bytes(product_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    pbg = _find_bgref_path(product_id)
    if not pbg:
        return None, None
    try:
        b = pbg.read_bytes()
        if not b:
            return None, None
        return b, _mime_for_path(pbg)
    except Exception:
        return None, None

def _find_realized_path(product_id: str) -> Optional[Path]:
    for ext in ["png", "jpg", "jpeg", "webp"]:
        p = PRODUCTS_DIR / f"{product_id}_real.{ext}"
        if p.exists():
            return p
    return None

def _realized_bytes(product_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    pr = _find_realized_path(product_id)
    if not pr:
        return None, None
    try:
        b = pr.read_bytes()
        if not b:
            return None, None
        return b, _mime_for_path(pr)
    except Exception:
        return None, None

def _save_realized(product_id: str, image_bytes: bytes, mime: str) -> str:
    ext = "png" if "png" in (mime or "").lower() else "jpg"
    p = PRODUCTS_DIR / f"{product_id}_real.{ext}"
    p.write_bytes(image_bytes)
    return str(p)

def _meta_path(product_id: str) -> Path:
    return PRODUCTS_META_DIR / f"{product_id}.json"

def _save_product_meta(product_id: str, meta: dict) -> None:
    _meta_path(product_id).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def _load_product_meta(product_id: str) -> dict:
    p = _meta_path(product_id)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

def _bg_path(bg_id: str) -> Path:
    for ext in ["png", "jpg", "jpeg", "webp"]:
        p = BACKGROUNDS_DIR / f"{bg_id}.{ext}"
        if p.exists():
            return p
    raise HTTPException(status_code=404, detail="Background ref no encontrado")

def _bg_bytes(bg_id: Optional[str]) -> Tuple[Optional[bytes], Optional[str]]:
    if not bg_id:
        return None, None
    try:
        p = _bg_path(bg_id)
        b = p.read_bytes()
        return b, _mime_for_path(p)
    except Exception:
        return None, None

def _extras_dir(product_id: str) -> Path:
    d = PRODUCTS_DIR / f"{product_id}_extras"
    d.mkdir(exist_ok=True)
    return d

def _save_extra_files(product_id: str, files: Optional[List[UploadFile]]) -> List[dict]:
    """
    Guarda extra files y devuelve lista de metadatos:
    [{ "idx": 1, "path": "...", "mime": "...", "filename": "..."}]
    """
    out = []
    if not files:
        return out
    
    d = _extras_dir(product_id)
    for i, f in enumerate(files, start=1):
        if not f or not getattr(f, "filename", None):
            continue
        if not f.content_type or not f.content_type.startswith("image/"):
            continue

        ext = (f.filename.split(".")[-1] if f.filename else "").lower()
        if ext not in ["png", "jpg", "jpeg", "webp"]:
            continue

        raw = f.file.read()
        if not raw:
            continue

        p = d / f"extra_{i}.{ext}"
        p.write_bytes(raw)

        out.append({
            "idx": i,
            "path": str(p),
            "mime": _mime_for_path(p),
            "filename": f.filename,
        })

    return out

def _load_extra_refs(product_id: str) -> List[dict]:
    meta = _load_product_meta(product_id) or {}
    refs = meta.get("extra_refs") or []
    if not isinstance(refs, list):
        return []
    # filtrar solo los que existen
    out = []
    for r in refs:
        try:
            p = Path(r.get("path"))
            if p.exists():
                out.append(r)
        except Exception:
            pass
    return out

def _parse_extra_labels(extra_labels_json: str, count: int) -> List[str]:
    """
    extra_labels_json ejemplo: ["bordado","estampa","cuello"]
    Si no viene o está roto, llena con "detalle_#"
    """
    labels = []
    try:
        arr = json.loads(extra_labels_json) if extra_labels_json else []
        if isinstance(arr, list):
            labels = [str(x).strip() for x in arr]
    except Exception:
        labels = []
    # normalizar tamaño
    out = []
    for i in range(count):
        lab = labels[i] if i < len(labels) and labels[i] else f"detalle_{i+1}"
        out.append(lab)
    return out

def _extract_image_bytes(resp) -> tuple[bytes, str]:
    if not getattr(resp, "candidates", None):
        raise HTTPException(status_code=500, detail="Gemini no devolvió candidates")

    for part in resp.candidates[0].content.parts:
        if getattr(part, "inline_data", None) is not None:
            mime = part.inline_data.mime_type or "image/png"
            return part.inline_data.data, mime

    raise HTTPException(status_code=500, detail="Gemini no devolvió imagen (inline_data vacío)")

def _save_output(image_bytes: bytes, mime: str) -> dict:
    image_id = str(uuid.uuid4())
    ext = "png" if "png" in (mime or "").lower() else "jpg"
    path = OUTPUT_DIR / f"{image_id}.{ext}"
    path.write_bytes(image_bytes)
    return {
        "image_id": image_id,
        "view_url": f"{API_BASE}/image/{image_id}",
        "mime": mime,
    }

def _safe_json_parse(txt: str) -> Dict[str, Any]:
    txt = (txt or "").strip()
    if not txt:
        return {}
    try:
        return json.loads(txt)
    except Exception:
        start = txt.find("{")
        end = txt.rfind("}")
        if start != -1 and end != -1 and end > start:
            chunk = txt[start : end + 1]
            try:
                return json.loads(chunk)
            except Exception:
                return {}
        return {}

# ----------------- Auto-descripción del producto (VISION) -----------------

def _auto_describe_product(product_bytes: bytes, product_mime: str, product_type_hint: str = "") -> Dict[str, Any]:
    """
    Devuelve un dict (JSON) con descripción detallada del producto para mejorar prompts.
    Importante: NO inventar; describir SOLO lo visible.
    """
    try:
        client = _client()
        hint = (product_type_hint or "").strip()

        instruction = f"""
Devolvé SOLO JSON válido (sin markdown, sin texto extra).

Tarea:
- Mirá la foto del producto y describílo con precisión, SOLO lo visible. NO inventes marcas ni texto.
- Esto se usa para mejorar prompts manteniendo el producto idéntico (product lock).

Si hay letras/logos, describilos como "logo/inscripción visible" sin inventar el contenido exacto si no es legible.

Usá este schema EXACTO:
{{
  "title_short": string,
  "category_guess": "bottle" | "shoes" | "apparel" | "furniture" | "jewelry" | "electronics" | "cosmetics" | "other",
  "product_description_long": string,
  "key_visual_features": [string],
  "materials": [string],
  "colors": [string],
  "finish_texture": [string],
  "prompt_boosters": [string]
}}

Reglas:
- product_description_long: 2-4 oraciones, bien visual (forma, partes, material, textura, detalles).
- prompt_boosters: 4-8 líneas cortas, accionables.
- Si te doy un hint, úsalo SOLO para orientar categoría, no para inventar: hint="{hint}".
""".strip()

        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                "IMAGEN (producto):",
                types.Part.from_bytes(data=product_bytes, mime_type=product_mime),
                instruction,
            ],
        )
        txt = getattr(resp, "text", None) or ""
        data = _safe_json_parse(txt)
        if not isinstance(data, dict) or not data:
            return {"error": "empty_or_invalid_json", "raw": (txt[:400] if txt else "")}

        def _as_list(x):
            if isinstance(x, list):
                return [str(i) for i in x if str(i).strip()]
            return []

        out = {
            "title_short": str(data.get("title_short") or "").strip(),
            "category_guess": str(data.get("category_guess") or "other").strip(),
            "product_description_long": str(data.get("product_description_long") or "").strip(),
            "key_visual_features": _as_list(data.get("key_visual_features")),
            "materials": _as_list(data.get("materials")),
            "colors": _as_list(data.get("colors")),
            "finish_texture": _as_list(data.get("finish_texture")),
            "prompt_boosters": _as_list(data.get("prompt_boosters")),
        }

        if not out["product_description_long"] and not out["prompt_boosters"]:
            out["error"] = "missing_core_fields"

        return out
    except Exception as e:
        return {"error": "exception", "detail": str(e)}

# ----------------- Recomendador -----------------

def _normalize_txt(s: str) -> str:
    return (s or "").strip().lower()

def _is_apparel(pt: str) -> bool:
    pt = _normalize_txt(pt)
    keys = [
        "remera","camisa","pantalon","pantalón","hoodie","buzo","ropa","vestido","campera",
        "jersey","musculosa","top","crop","tank","indumentaria","tee","t-shirt","tshirt"
    ]
    return any(k in pt for k in keys)

def _is_shoes(pt: str) -> bool:
    pt = _normalize_txt(pt)
    return any(k in pt for k in ["zapat", "sneaker", "calzado", "zapato", "botin", "botín"])

def _is_bottle(pt: str) -> bool:
    pt = _normalize_txt(pt)
    return any(k in pt for k in ["botella", "vidrio", "glass", "termo"])

def _is_furniture(pt: str) -> bool:
    pt = _normalize_txt(pt)
    return any(k in pt for k in ["sillon", "sillón", "sofa", "sofá", "mesa", "silla", "mueble"])

def _prefill_custom_text(product_type: str, aesthetic: str) -> str:
    pt = _normalize_txt(product_type)
    aest = _normalize_txt(aesthetic) or "minimalista"

    aest_base = {
        "minimalista": "fondo limpio, colores neutros, props mínimos, estética premium simple",
        "clean": "set limpio, luz suave, sombras reales, sin props innecesarios",
        "premium": "superficie premium (mármol/hormigón fino), reflejos suaves, look high-end",
        "moderno": "set moderno, líneas simples, materiales contemporáneos",
        "luxury": "look luxury, superficies nobles, reflejos controlados, contraste suave",
        "rustico": "madera natural, textura cálida, luz natural suave",
        "rústico": "madera natural, textura cálida, luz natural suave",
    }.get(aest, "set limpio, luz suave, sombras reales")

    if _is_bottle(pt):
        extra = "reflejos/vidrio realistas, etiqueta legible sin inventar, sin condensación falsa, sin deformar el vidrio"
    elif _is_shoes(pt):
        extra = "detalle de costuras/mesh, suela visible en una toma, sin deformar la silueta, textura real"
    elif _is_apparel(pt):
        extra = "tela realista, caída natural, costuras nítidas, print integrado en la tela (no sticker), pliegues naturales"
    elif _is_furniture(pt):
        extra = "material realista (tela/cuero), sombras reales en el piso, escala correcta, sin deformaciones"
    else:
        extra = "texturas naturales, sombras coherentes, cero look IA, sin artefactos"

    return f"{aest_base}. {extra}."

def _recommended_config(product_type: str, aesthetic: str) -> Dict[str, Any]:
    pt = _normalize_txt(product_type)
    aest = _normalize_txt(aesthetic) or "minimalista"

    env_type = "studio"
    scene = "white"
    style = "ecommerce"
    lighting = "studio_soft"
    chips: List[str] = []

    if aest in ["minimalista", "clean"]:
        chips = ["clean", "minimal"]
    elif aest in ["premium", "luxury"]:
        chips = ["premium", "luxury"]
        scene = "gradient"
    elif aest in ["moderno"]:
        chips = ["modern", "clean"]
        scene = "gray"
    elif "rust" in aest or "rúst" in aest:
        chips = ["rustic", "clean"]
        env_type = "lifestyle"
        scene = "home"
        lighting = "natural"

    if _is_bottle(pt):
        env_type = "studio"
        scene = "gradient" if aest in ["premium", "luxury"] else "white"
        lighting = "premium" if aest in ["premium", "luxury"] else "studio_soft"
        style = "ecommerce"
    elif _is_shoes(pt):
        env_type = "studio"
        scene = "gray"
        lighting = "studio_soft"
        style = "advertising" if aest in ["premium", "luxury"] else "ecommerce"
        chips = list(dict.fromkeys(chips + ["modern"]))
    elif _is_apparel(pt):
        env_type = "studio"  # mejor para vender ropa (limpio y controlado)
        scene = "white" if aest in ["minimalista", "clean"] else "gray"
        lighting = "studio_soft" if aest in ["minimalista", "clean"] else "premium"
        style = "instagram_ads"
        chips = list(dict.fromkeys(chips + ["clean"]))
    elif _is_furniture(pt):
        env_type = "indoor_real"
        scene = "living_room"
        lighting = "natural"
        style = "lifestyle"
        chips = list(dict.fromkeys(chips + ["clean"]))

    if scene not in SCENES_BY_TYPE.get(env_type, set()):
        scene = sorted(list(SCENES_BY_TYPE.get(env_type, {"white"})))[0]

    return {
        "environment": {"type": env_type, "scene": scene, "chips": chips},
        "style": style,
        "lighting": lighting,
        "model_defaults": {
            "enabled": False,
            "gender": "female",
            "age_range": "25-35",
            "appearance": "",
        },
    }

# ----------------- Prompt builder -----------------

def _infer_is_apparel_from_meta(meta: Dict[str, Any]) -> bool:
    pt = (meta.get("product_type") or "")
    if _is_apparel(pt):
        return True
    auto = meta.get("auto_product_desc") or {}
    if isinstance(auto, dict):
        if (auto.get("category_guess") or "").strip().lower() == "apparel":
            return True
        title = (auto.get("title_short") or "").lower()
        if any(k in title for k in ["remera","camisa","top","crop","tank","tshirt","t-shirt","tee"]):
            return True
    return False

def _build_instruction(
    req: GenerateFromProductConfigRequest,
    has_secondary: bool = False,
    meta: Optional[Dict[str, Any]] = None,
    has_bgref: bool = False,
    has_extras: bool = False,
) -> str:
    meta = meta or {}
    is_apparel = _infer_is_apparel_from_meta(meta)

    chips_txt = ", ".join([c.strip() for c in req.environment.chips if c.strip()])
    custom = (req.environment.custom_text or "").strip()
    scene_text = (getattr(req.environment, "scene_text", "") or "").strip()

    auto_desc = meta.get("auto_product_desc") if isinstance(meta.get("auto_product_desc"), dict) else {}
    boosters = []
    if isinstance(auto_desc, dict):
        boosters = auto_desc.get("prompt_boosters") if isinstance(auto_desc.get("prompt_boosters"), list) else []
    boosters_txt = "\n".join([f"- {str(b).strip()}" for b in boosters[:10] if str(b).strip()])

    if req.model and req.model.enabled:
        gender = req.model.gender or "female"
        age = req.model.age_range or "25-35"
        appearance = (req.model.appearance or "").strip()
        model_txt = (
            "Modelo/persona: SÍ.\n"
            f"- Género: {gender}\n"
            f"- Edad: {age}\n"
            + (f"- Apariencia/estilo: {appearance}\n" if appearance else "")
            + "- Regla: la persona NO debe tapar el producto. Presencia sutil si aplica.\n"
            + "- Regla: mantener identidad consistente en todo el pack (misma persona).\n"
        )
    else:
        model_txt = "Modelo/persona: NO."

    base = f"""
Contexto de toma:
- Estilo: {req.style}
- Iluminación: {req.lighting}
""".strip()

    if has_bgref:
        base += "\n- Fondo/Set: usar la IMAGEN DE REFERENCIA (background ref) como fuente de verdad.\n"
    elif scene_text:
        base += f"""
- ESCENARIO (texto libre, OBLIGATORIO): {scene_text}
- REGLA: el escenario debe coincidir EXACTAMENTE con el texto libre (no reemplazar por otra cosa similar).
- REGLA: NO convertir el escenario en "gym", "studio", "living room", etc. a menos que el texto libre lo pida.
""".strip()
    else:
        base += f"""
- Ambiente: {req.environment.type}
- Escena/fondo: {req.environment.scene}
""".strip()

    if chips_txt:
        base += f"\n- Elementos/mood: {chips_txt}"
    if custom:
        base += f"\n- Detalles extra: {custom}"

    product_long = ""
    if isinstance(auto_desc, dict):
        product_long = (auto_desc.get("product_description_long") or "").strip()

    product_block = ""
    if product_long or boosters_txt:
        product_block = "\n\nDETALLES DEL PRODUCTO (AUTO - NO INVENTAR):\n"
        if product_long:
            product_block += f"- Descripción: {product_long}\n"
        if boosters_txt:
            product_block += "- Boosters:\n" + boosters_txt + "\n"

    instruction = (
        "INSTRUCCIONES IMPORTANTES (prioridad de arriba hacia abajo):\n"
        + (BACKGROUND_REF_LOCK_CLAUSE + "\n" if has_bgref else "")
        + (MULTIVIEW_CLAUSE if has_secondary else "")
        + ("\n" + DEMOCKUP_CLAUSE + "\n" if is_apparel else "")
        + (EXTRA_REFS_CLAUSE if has_extras else "")
        + LOCK_PRODUCT_CLAUSE
        + NO_TEXT_CLAUSE
        + HYPERREALISM_CLAUSE
        + CONSISTENCY_CLAUSE
        + ("\n" + MODEL_IDENTITY_LOCK_CLAUSE if (req.model and req.model.enabled) else "")
        + (product_block if product_block else "")
        + "\n\n"
        + base
        + "\n\n"
        + model_txt
        + "\n\nResultado: foto publicitaria profesional, hiperrealista, lista para e-commerce."
    )
    return instruction.strip()

def _generate_image_with_prompt(
    product_bytes: bytes,
    mime: str,
    instruction: str,
    secondary_bytes: Optional[bytes] = None,
    secondary_mime: Optional[str] = None,
    bgref_bytes: Optional[bytes] = None,
    bgref_mime: Optional[str] = None,
    hero_ref_bytes: Optional[bytes] = None,
    hero_ref_mime: Optional[str] = None,
    extra_refs: Optional[List[dict]] = None,
) -> Tuple[bytes, str]:
    client = _client()

    contents: List[Any] = []
    contents.append("IMAGEN 1 (producto principal):")
    contents.append(types.Part.from_bytes(data=product_bytes, mime_type=mime))

    if secondary_bytes and secondary_mime:
        contents.append("IMAGEN 2 (vista secundaria del MISMO producto):")
        contents.append(types.Part.from_bytes(data=secondary_bytes, mime_type=secondary_mime))

    if bgref_bytes and bgref_mime:
        contents.append("IMAGEN DE REFERENCIA DE FONDO/SET (background reference):")
        contents.append(types.Part.from_bytes(data=bgref_bytes, mime_type=bgref_mime))

    # HERO visual anchor (para replicar set/modelo en el pack)
    if hero_ref_bytes and hero_ref_mime:
        contents.append("IMAGEN HERO (referencia del set y/o modelo):")
        contents.append(types.Part.from_bytes(data=hero_ref_bytes, mime_type=hero_ref_mime))

    if extra_refs:
        for r in extra_refs[:6]:  # cap a 6 extras para no perder coherencia
            try:
                p = Path(r["path"])
                b = p.read_bytes()
                m = r.get("mime") or _mime_for_path(p)
                label = (r.get("label") or "detalle").strip()
                contents.append(f"IMAGEN EXTRA (DETALLE) - etiqueta: {label}")
                contents.append(types.Part.from_bytes(data=b, mime_type=m))
            except Exception:
                continue

    contents.append(instruction)

    resp = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=contents,
    )
    return _extract_image_bytes(resp)

def _qc_eval(product_bytes: bytes, product_mime: str, gen_bytes: bytes, gen_mime: str) -> Dict[str, Any]:
    try:
        client = _client()
        instruction = """
Devolvé SOLO JSON válido (sin markdown).

Compará la imagen ORIGINAL del producto vs la imagen GENERADA.
Evaluar:
1) hiperrealismo fotográfico (parece foto real, sin look IA/CGI)
2) diseño/identidad del producto preservada (colores, print, proporciones, detalles visibles)
3) (si apparel mockup) que ya NO parezca mockup

Schema:
{
  "photorealism_score": number,
  "product_locked_score": number,
  "demockup_score": number,
  "issues": [string],
  "verdict": "pass" | "fail"
}

Reglas:
- FAIL si photorealism_score < 85 o product_locked_score < 90.
- Si se ve mockup (plano/recorte perfecto), demockup_score < 85 => FAIL.
- Sé estricto con artefactos, halos, bordes raros, texturas falsas, cambios de color o del print.
"""
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                "IMAGEN ORIGINAL (producto):",
                types.Part.from_bytes(data=product_bytes, mime_type=product_mime),
                "IMAGEN GENERADA:",
                types.Part.from_bytes(data=gen_bytes, mime_type=gen_mime),
                instruction,
            ],
        )
        txt = getattr(resp, "text", None) or ""
        data = _safe_json_parse(txt)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}

def _qc_model_identity(hero_bytes: bytes, hero_mime: str, gen_bytes: bytes, gen_mime: str) -> Dict[str, Any]:
    try:
        client = _client()
        instruction = """
Devolvé SOLO JSON válido (sin markdown).

Compará la PERSONA/MODELO de la imagen HERO vs la imagen GENERADA.
Evaluar identidad facial: ¿es la MISMA persona?

Schema:
{
  "identity_score": number,
  "issues": [string],
  "verdict": "pass" | "fail"
}

Reglas:
- FAIL si identity_score < 90.
- Sé estricto: si cambian facciones, edad aparente, pelo, cejas, nariz, mandíbula, tono de piel => bajar score.
- Si la cara no se ve, pero lo visible coincide y no hay contradicción fuerte: PASS con 90-95.
"""
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                "IMAGEN HERO (referencia de modelo):",
                types.Part.from_bytes(data=hero_bytes, mime_type=hero_mime),
                "IMAGEN GENERADA:",
                types.Part.from_bytes(data=gen_bytes, mime_type=gen_mime),
                instruction,
            ],
        )
        txt = getattr(resp, "text", None) or ""
        data = _safe_json_parse(txt)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _reinforce_for_retry(instruction: str, qc: Dict[str, Any]) -> str:
    issues = qc.get("issues") if isinstance(qc, dict) else None
    issues_txt = ", ".join(issues[:8]) if isinstance(issues, list) else ""

    reinforcement = f"""
REINTENTO (corregir fallas) - OBLIGATORIO:
- Si hay cualquier look IA/CGI, hacerlo más fotográfico (sin halos, sin texturas falsas).
- Si el producto/diseño cambió aunque sea mínimo (print, colores, proporciones): revertir a EXACTO.
- Si la prenda se ve mockup/plana: convertir a prenda REAL (textura, caída, costuras, sombra real).
- Corregir específicamente: {issues_txt or "artefactos / no-foto / cambios de diseño / look mockup"}.
- Mantener MISMA escena/estilo/iluminación seleccionados; NO cambiar el concepto.
"""
    return (instruction + "\n\n" + reinforcement).strip()

def _demockup_to_real_apparel(
    product_bytes: bytes,
    product_mime: str,
    meta: Dict[str, Any],
    secondary_bytes: Optional[bytes] = None,
    secondary_mime: Optional[str] = None,
) -> Tuple[bytes, str, Dict[str, Any]]:
    """
    Convierte un mockup plano en una foto realista de prenda (base).
    Importante: mantener DISEÑO/PRINT exactamente igual.
    """
    client = _client()

    auto_desc = meta.get("auto_product_desc") if isinstance(meta.get("auto_product_desc"), dict) else {}
    product_long = (auto_desc.get("product_description_long") or "").strip()

    instruction = f"""
INSTRUCCIONES (PRIORIDAD MÁXIMA):
- Esto ES un mockup/plano digital. Tenés que transformarlo en una FOTO REAL de una prenda real.
- Mantener EXACTAMENTE el diseño: mismo texto/logo, misma posición, tamaño relativo y colores. NO CAMBIAR EL ARTE.
- Convertir soporte: tela real con textura visible, micro-arrugas naturales, caída real, costuras reales, bordes naturales (NO recorte perfecto).
- Debe haber sombra real y volumen real (nada "pegado").
- Prohibido look mockup: silueta perfecta, sombras pintadas, iluminación plana, bordes vectoriales.
- Fondo: estudio neutro (blanco/gris suave), iluminación de estudio suave, hiperrealista.

Si hay 2da imagen, úsala para confirmar detalles (ej espalda / etiqueta), sin inventar.

{("DETALLE DEL PRODUCTO (auto): " + product_long) if product_long else ""}

{LOCK_PRODUCT_CLAUSE}
{NO_TEXT_CLAUSE}
{HYPERREALISM_CLAUSE}

Salida esperada:
- UNA foto base hiperrealista (prenda real fotografiada), lista para usar como referencia en un photoshoot.
""".strip()

    contents: List[Any] = []
    contents.append("IMAGEN 1 (mockup original):")
    contents.append(types.Part.from_bytes(data=product_bytes, mime_type=product_mime))

    if secondary_bytes and secondary_mime:
        contents.append("IMAGEN 2 (vista secundaria del MISMO producto):")
        contents.append(types.Part.from_bytes(data=secondary_bytes, mime_type=secondary_mime))

    contents.append(instruction)

    resp = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=contents,
    )
    gen_bytes, gen_mime = _extract_image_bytes(resp)

    qc = _qc_eval(product_bytes, product_mime, gen_bytes, gen_mime) or {}
    return gen_bytes, gen_mime, qc

# ===================== PACK VARIATIONS (anti-duplicados) =====================

def _apparel_shot_plan(has_secondary: bool, model_on: bool) -> List[str]:
    """
    Plan fijo para apparel: 5 tomas verdaderamente distintas.
    Si n > 5, se repite con variaciones, pero el front normalmente usa 5.
    """
    plan = [
        "SHOT #1 HERO: frente 0°, encuadre medio, prenda protagonista. Sombra real y textura visible.",
        "SHOT #2 ANGULO 3/4: rotación ~25°, leve desplazamiento, mostrar volumen/costado. Fondo idéntico.",
        "SHOT #3 CLOSE-UP PRINT: acercamiento al logo/estampado + textura de tela (rib/algodón) con nitidez real.",
        "SHOT #4 DETALLE CONSTRUCCIÓN: costura, cuello, breteles/terminaciones, borde inferior con caída (NO recorte).",
    ]
    if has_secondary:
        plan.append("SHOT #5 VISTA SECUNDARIA OBLIGATORIA: usar Imagen 2 como guía principal (ej: espalda). Mostrar claramente esa vista.")
    else:
        # sin segunda, pedimos un flatlay/hanger alternativo que cambie composición fuerte
        plan.append("SHOT #5 COMPOSICIÓN DIFERENTE: flatlay natural o colgada en percha, ángulo top-down suave. Mantener set idéntico.")
    if model_on:
        # reforzar que si hay modelo, que se evite cara si no mantiene identidad
        plan.append("NOTA MODELO: si no podés mantener identidad 100%, evitar cara (crop cuello para abajo).")
    return plan

def _generic_shot_plan(has_secondary: bool) -> List[str]:
    plan = [
        "SHOT #1 HERO: packshot limpio, producto centrado, fondo y luz controlados.",
        "SHOT #2 3/4: ángulo 3/4, rotación ~20°, encuadre medio, DOF suave.",
        "SHOT #3 CLOSE-UP: detalle crítico (textura/etiqueta/logo/costura), enfoque muy nítido.",
        "SHOT #4 TOP-DOWN: cámara ligeramente más alta (semi top-down), encuadre más abierto.",
    ]
    if has_secondary:
        plan.append("SHOT #5 VISTA SECUNDARIA OBLIGATORIA: usar Imagen 2 como referencia principal para mostrar el otro lado/ángulo.")
    else:
        plan.append("SHOT #5 PERFIL: perfil lateral (rotación ~90°), encuadre medio, misma escena.")
    return plan

def _build_pack_shot_instruction(
    base_instruction: str,
    shot_line: str,
    used_signatures: List[str],
) -> str:
    used_txt = "\n".join([f"- {s}" for s in used_signatures[-8:]]) if used_signatures else "- (ninguna todavía)"
    return (
        base_instruction
        + "\n\nMODO PACK (OBLIGATORIO - ANTI DUPLICADOS):\n"
        + "- Mantener EXACTAMENTE el mismo set (fondo/props/luz/paleta). Prohibido cambiar locación.\n"
        + "- Esta toma debe ser CLARAMENTE distinta: cambiar ángulo de cámara, distancia, encuadre y/o foco.\n"
        + "- Si la toma se parece a una anterior (mismo ángulo/encuadre), ES INVÁLIDA: cambiá ángulo al menos 25°, y cambiá encuadre (más abierto o más cerrado) obligatoriamente.\n"
        + "- Para close-up: el producto debe ocupar >70% del frame.\n"
        + "- Para abierto: el producto debe ocupar <40% del frame y mostrar más entorno.\n"
        + "- Prohibido repetir una toma anterior.\n"
        + "TOMAS YA GENERADAS (NO REPETIR):\n"
        + used_txt
        + "\n\nTOMA ACTUAL (OBLIGATORIA):\n"
        + f"- {shot_line}\n"
        + "- Resultado: foto real hiperrealista del mismo shoot, distinta a las demás.\n"
    ).strip()


# ===================== ROUTES =====================

@app.get("/")
def home():
    return {"ok": True}

@app.get("/options")
def get_options():
    return {
        "environment_types": list(SCENES_BY_TYPE.keys()),
        "scenes_by_type": {k: sorted(list(v)) for k, v in SCENES_BY_TYPE.items()},
        "chips": CHIPS,
        "styles": STYLES,
        "lightings": LIGHTINGS,
        "model": {"genders": ["female", "male"], "age_ranges": ["baby", "10-18", "18-24", "25-35", "36-50", "50+"]},
    }

@app.get("/presets")
def list_presets():
    return {"presets": [{"key": k, "title": v["title"]} for k, v in PRESETS.items()]}

@app.post("/upload-product")
def upload_product(
    file: UploadFile = File(...),
    file2: Optional[UploadFile] = File(None),
    extra_files: Optional[List[UploadFile]] = File(None),
    extra_labels: str = Form(""),
    product_type: str = Form(""),
    aesthetic: str = Form("minimalista"),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Debe ser imagen")

    ext = (file.filename.split(".")[-1] if file.filename else "").lower()
    if ext not in ["png", "jpg", "jpeg", "webp"]:
        raise HTTPException(status_code=400, detail="Formato no soportado")

    product_id = str(uuid.uuid4())

    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    path = PRODUCTS_DIR / f"{product_id}.{ext}"
    path.write_bytes(raw)

    # secundaria opcional
    has_secondary = False
    if file2 is not None and file2.filename:
        ext2 = (file2.filename.split(".")[-1] if file2.filename else "").lower()
        if ext2 in ["png", "jpg", "jpeg", "webp"]:
            raw2 = file2.file.read()
            if raw2:
                (PRODUCTS_DIR / f"{product_id}_2.{ext2}").write_bytes(raw2)
                has_secondary = True

    # extras opcionales (N)
    extra_refs = []
    if extra_files:
        saved_refs = _save_extra_files(product_id, extra_files)
        labels = _parse_extra_labels(extra_labels, len(saved_refs))
        for r, lab in zip(saved_refs, labels):
            r["label"] = lab
        extra_refs = saved_refs

    prefill = _prefill_custom_text(product_type, aesthetic)
    reco = _recommended_config(product_type, aesthetic)

    product_mime = _mime_for_path(path)
    auto_desc = _auto_describe_product(raw, product_mime, product_type_hint=(product_type or "").strip())
    auto_desc_created_at = datetime.now(timezone.utc).isoformat()

    meta = {
        "product_id": product_id,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "stored_file": str(path),
        "created_at": datetime.now(timezone.utc).isoformat(),

        "product_type": (product_type or "").strip(),
        "aesthetic": (aesthetic or "minimalista").strip(),

        "has_secondary": has_secondary,
        "secondary_file": str(_find_secondary_path(product_id)) if has_secondary else None,

        "extra_refs": extra_refs,

        "prefill_custom_text": prefill,
        "recommended_config": reco,

        "auto_product_desc": auto_desc,
        "auto_product_desc_created_at": auto_desc_created_at,

        "tags": [],
        "notes": "",
    }
    _save_product_meta(product_id, meta)

    return {
        "ok": True,
        "product_id": product_id,
        "has_secondary": has_secondary,
        "extras_count": len(extra_refs),
        "view_url": f"{API_BASE}/product/{product_id}",
    }

@app.get("/product/{product_id}")
def get_product(product_id: str):
    p = _find_product_path(product_id)
    return Response(p.read_bytes(), media_type=_mime_for_path(p))

@app.get("/product-meta/{product_id}")
def get_product_meta(product_id: str):
    _ = _find_product_path(product_id)
    meta = _load_product_meta(product_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Meta no encontrada")
    return {"ok": True, "meta": meta}

@app.get("/image/{image_id}")
def get_image(image_id: str):
    for ext in ["png", "jpg"]:
        p = OUTPUT_DIR / f"{image_id}.{ext}"
        if p.exists():
            mt = "image/png" if ext == "png" else "image/jpeg"
            return Response(p.read_bytes(), media_type=mt)
    raise HTTPException(status_code=404, detail="Imagen no encontrada")

@app.post("/upload-background-ref")
def upload_background_ref(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Debe ser imagen")

    ext = (file.filename.split(".")[-1] if file.filename else "").lower()
    if ext not in ["png", "jpg", "jpeg", "webp"]:
        raise HTTPException(status_code=400, detail="Formato no soportado")

    bg_id = str(uuid.uuid4())
    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    (BACKGROUNDS_DIR / f"{bg_id}.{ext}").write_bytes(raw)
    return {"ok": True, "background_ref_id": bg_id, "view_url": f"{API_BASE}/background/{bg_id}"}

@app.get("/background/{bg_id}")
def get_background(bg_id: str):
    p = _bg_path(bg_id)
    return Response(p.read_bytes(), media_type=_mime_for_path(p))

@app.post("/generate-from-product-preset")
def generate_from_product_preset(req: GeneratePresetRequest):
    if req.preset not in PRESETS:
        raise HTTPException(status_code=400, detail="Preset inválido")

    p = _find_product_path(req.product_id)
    product_bytes = p.read_bytes()
    mime = _mime_for_path(p)

    meta = _load_product_meta(req.product_id) or {}
    bg_bytes, bg_mime = _bgref_bytes(req.product_id)
    has_bgref = bool(bg_bytes and bg_mime)

    # ✅ BLOQUEO: si hay bg_ref, no permitir presets
    if has_bgref:
        raise HTTPException(
            status_code=400,
            detail="No se puede usar preset cuando hay foto de referencia de fondo (bg_ref). Usá generate-from-product-config o generate-pack."
        )

    instruction = (
        "INSTRUCCIONES IMPORTANTES:\n"
        + (BACKGROUND_REF_LOCK_CLAUSE + "\n" if has_bgref else "")
        + LOCK_PRODUCT_CLAUSE
        + NO_TEXT_CLAUSE
        + HYPERREALISM_CLAUSE
        + CONSISTENCY_CLAUSE
        + "\n"
        + "Preset:\n"
        + PRESETS[req.preset]["prompt"]
        + "\nResultado: foto publicitaria profesional, hiperrealista, lista para e-commerce."
    )

    gen_bytes, out_mime = _generate_image_with_prompt(
        product_bytes, mime, instruction,
        secondary_bytes=None, secondary_mime=None,
        bgref_bytes=bg_bytes, bgref_mime=bg_mime
    )
    saved = _save_output(gen_bytes, out_mime)
    return {"ok": True, **saved, "preset": req.preset, "prompt_used": instruction}

@app.post("/generate-from-product-config")
def generate_from_product_config(req: GenerateFromProductConfigRequest):
    # Prioridad: background_ref_id > scene_text > scene preset
    bg_bytes, bg_mime = _bg_bytes(req.background_ref_id)
    has_bgref = bool(bg_bytes and bg_mime)

    if (not has_bgref) and (req.environment.scene not in SCENES_BY_TYPE.get(req.environment.type, set())):
        raise HTTPException(status_code=400, detail="Escena inválida para ese environment.type")

    product_path = _find_product_path(req.product_id)
    product_bytes = product_path.read_bytes()
    product_mime = _mime_for_path(product_path)

    meta = _load_product_meta(req.product_id) or {}

    sec_bytes, sec_mime = _secondary_bytes(req.product_id)
    has_secondary = bool(sec_bytes and sec_mime)

    extra_refs = _load_extra_refs(req.product_id)
    has_extras = len(extra_refs) > 0

    instruction = _build_instruction(req, has_secondary=has_secondary, meta=meta, has_bgref=has_bgref, has_extras=has_extras)

    gen_bytes, out_mime = _generate_image_with_prompt(
        product_bytes, product_mime, instruction,
        secondary_bytes=sec_bytes, secondary_mime=sec_mime,
        bgref_bytes=bg_bytes, bgref_mime=bg_mime,
        extra_refs=extra_refs
    )

    qc = _qc_eval(product_bytes, product_mime, gen_bytes, out_mime) or {}
    attempts = 1

    while attempts < 3:
        if not qc:
            break
        if qc.get("verdict") == "pass":
            break
        instruction = _reinforce_for_retry(instruction, qc)
        gen_bytes, out_mime = _generate_image_with_prompt(
            product_bytes, product_mime, instruction,
            secondary_bytes=sec_bytes, secondary_mime=sec_mime,
            bgref_bytes=bg_bytes, bgref_mime=bg_mime,
            extra_refs=extra_refs
        )
        qc = _qc_eval(product_bytes, product_mime, gen_bytes, out_mime) or qc
        attempts += 1

    saved = _save_output(gen_bytes, out_mime)
    return {"ok": True, **saved, "prompt_used": instruction, "qc": qc, "attempts": attempts}

@app.post("/generate-pack")
def generate_pack(req: GeneratePackRequest):
    n = max(2, min(int(req.n or 5), 10))

    # Prioridad: background_ref_id > scene_text > scene preset
    bg_bytes, bg_mime = _bg_bytes(req.background_ref_id)
    has_bgref = bool(bg_bytes and bg_mime)

    if (not has_bgref) and (req.environment.scene not in SCENES_BY_TYPE.get(req.environment.type, set())):
        raise HTTPException(status_code=400, detail="Escena inválida para ese environment.type")

    product_path = _find_product_path(req.product_id)
    product_bytes = product_path.read_bytes()
    product_mime = _mime_for_path(product_path)

    meta = _load_product_meta(req.product_id) or {}
    is_apparel = _infer_is_apparel_from_meta(meta)

    sec_bytes, sec_mime = _secondary_bytes(req.product_id)
    has_secondary = bool(sec_bytes and sec_mime)

    extra_refs = _load_extra_refs(req.product_id)
    has_extras = len(extra_refs) > 0

    # --- DEMOCKUP AUTO (APPAREL): si es ropa, primero genero una base realista y la uso como referencia principal ---
    realized_b, realized_m = _realized_bytes(req.product_id)

    if is_apparel and not (realized_b and realized_m):
        demock_bytes, demock_mime, demock_qc = _demockup_to_real_apparel(
            product_bytes, product_mime, meta, sec_bytes, sec_mime
        )

        # si salió muy mockup igual, forzá un segundo intento más fuerte
        if demock_qc and demock_qc.get("verdict") == "fail":
            demock_bytes2, demock_mime2, _ = _demockup_to_real_apparel(
                product_bytes, product_mime, meta, sec_bytes, sec_mime
            )
            demock_bytes, demock_mime = demock_bytes2, demock_mime2

        real_path = _save_realized(req.product_id, demock_bytes, demock_mime)
        meta["realized_file"] = real_path
        meta["realized_created_at"] = datetime.now(timezone.utc).isoformat()
        _save_product_meta(req.product_id, meta)

        realized_b, realized_m = demock_bytes, demock_mime

    # si hay realized, PASA a ser tu "producto principal" para el shoot
    if is_apparel and (realized_b and realized_m):
        product_bytes_for_shoot = realized_b
        product_mime_for_shoot = realized_m
        # mantenemos el mockup original como "referencia de diseño" en secondary slot si NO hay sec
        design_ref_bytes = product_bytes
        design_ref_mime = product_mime
    else:
        product_bytes_for_shoot = product_bytes
        product_mime_for_shoot = product_mime
        design_ref_bytes = None
        design_ref_mime = None

    base_instruction = _build_instruction(
        GenerateFromProductConfigRequest(
            product_id=req.product_id,
            environment=req.environment,
            style=req.style,
            lighting=req.lighting,
            model=req.model,
            background_ref_id=req.background_ref_id,
        ),
        has_secondary=has_secondary,
        meta=meta,
        has_bgref=has_bgref,
        has_extras=has_extras
    )

    # Shot plan fijo y anti-repetición
    plan = _apparel_shot_plan(has_secondary=has_secondary, model_on=bool(req.model and req.model.enabled)) if is_apparel else _generic_shot_plan(has_secondary)

    images = []
    used_signatures: List[str] = []

    # HERO
    hero_shot = plan[0]
    hero_instruction = _build_pack_shot_instruction(base_instruction, hero_shot, used_signatures)

    gen_bytes, out_mime = _generate_image_with_prompt(
        product_bytes_for_shoot, product_mime_for_shoot, hero_instruction,
        secondary_bytes=sec_bytes if sec_bytes else design_ref_bytes,
        secondary_mime=sec_mime if sec_mime else design_ref_mime,
        bgref_bytes=bg_bytes, bgref_mime=bg_mime,
        extra_refs=extra_refs
    )
    hero_bytes, hero_mime = gen_bytes, out_mime

    qc = _qc_eval(product_bytes, product_mime, gen_bytes, out_mime) or {}
    attempts = 1
    while attempts < 3:
        if not qc or qc.get("verdict") == "pass":
            break
        hero_instruction = _reinforce_for_retry(hero_instruction, qc)
        gen_bytes, out_mime = _generate_image_with_prompt(
            product_bytes_for_shoot, product_mime_for_shoot, hero_instruction,
            secondary_bytes=sec_bytes if sec_bytes else design_ref_bytes,
            secondary_mime=sec_mime if sec_mime else design_ref_mime,
            bgref_bytes=bg_bytes, bgref_mime=bg_mime,
            extra_refs=extra_refs
        )
        qc = _qc_eval(product_bytes, product_mime, gen_bytes, out_mime) or qc
        hero_bytes, hero_mime = gen_bytes, out_mime
        attempts += 1

    saved = _save_output(hero_bytes, hero_mime)
    used_signatures.append(hero_shot)

    images.append({
        "image_id": saved["image_id"],
        "view_url": saved["view_url"],
        "mime": saved["mime"],
        "index": 1,
        "role": "hero",
        "prompt_used": hero_instruction,
        "qc": qc,
        "attempts": attempts,
        "shot_hint": hero_shot,
    })

    # RESTO DEL PACK
    for i in range(1, n):
        shot_line = plan[i % len(plan)]
        instr = _build_pack_shot_instruction(base_instruction, shot_line, used_signatures)

        gen_bytes, out_mime = _generate_image_with_prompt(
            product_bytes_for_shoot, product_mime_for_shoot, instr,
            secondary_bytes=sec_bytes if sec_bytes else design_ref_bytes,
            secondary_mime=sec_mime if sec_mime else design_ref_mime,
            bgref_bytes=bg_bytes, bgref_mime=bg_mime,
            hero_ref_bytes=hero_bytes, hero_ref_mime=hero_mime,
            extra_refs=extra_refs
        )

        qc = _qc_eval(product_bytes, product_mime, gen_bytes, out_mime) or {}
        model_qc = {}
        if req.model and req.model.enabled:
            model_qc = _qc_model_identity(hero_bytes, hero_mime, gen_bytes, out_mime) or {}

        attempts = 1
        while attempts < 3:
            product_ok = (not qc) or (qc.get("verdict") == "pass")
            model_ok = True
            if req.model and req.model.enabled:
                model_ok = (not model_qc) or (model_qc.get("verdict") == "pass")

            if product_ok and model_ok:
                break

            instr = _reinforce_for_retry(instr, qc)

            if req.model and req.model.enabled and model_qc and model_qc.get("verdict") == "fail":
                issues = model_qc.get("issues") if isinstance(model_qc.get("issues"), list) else []
                instr = (instr + "\n\nREINTENTO IDENTIDAD MODELO (OBLIGATORIO):\n"
                         + "- Debe ser EXACTAMENTE la misma persona que en la HERO.\n"
                         + "- Si no se mantiene, evitar cara (crop cuello para abajo) antes que cambiar identidad.\n"
                         + "- Corregir: " + (", ".join(issues[:8]) if issues else "cambios de facciones") + "\n").strip()

            gen_bytes, out_mime = _generate_image_with_prompt(
                product_bytes_for_shoot, product_mime_for_shoot, instr,
                secondary_bytes=sec_bytes if sec_bytes else design_ref_bytes,
                secondary_mime=sec_mime if sec_mime else design_ref_mime,
                bgref_bytes=bg_bytes, bgref_mime=bg_mime,
                hero_ref_bytes=hero_bytes, hero_ref_mime=hero_mime
            )

            qc = _qc_eval(product_bytes, product_mime, gen_bytes, out_mime) or qc
            if req.model and req.model.enabled:
                model_qc = _qc_model_identity(hero_bytes, hero_mime, gen_bytes, out_mime) or model_qc

            attempts += 1

        saved = _save_output(gen_bytes, out_mime)
        used_signatures.append(shot_line)

        images.append({
            "image_id": saved["image_id"],
            "view_url": saved["view_url"],
            "mime": saved["mime"],
            "index": i + 1,
            "role": "match",
            "prompt_used": instr,
            "qc": qc,
            "model_qc": model_qc,
            "attempts": attempts,
            "shot_hint": shot_line,
        })

    return {"ok": True, "n": n, "images": images}
