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

class GeneratePackRequest(BaseModel):
    product_id: str
    environment: EnvironmentConfig
    style: StyleType = "ecommerce"
    lighting: LightingType = "studio_soft"
    model: ModelConfig = ModelConfig(enabled=False)
    n: int = 5

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
- El producto debe quedar IDENTICO al original: misma forma, proporciones, textura, costuras, etiquetas, logo, tipografías existentes, colores exactos.
- NO inventes partes, NO borres detalles, NO deformes bordes, NO cambies materiales.
- No “mejores” el producto: solo cambia entorno, luz y composición.
"""

NO_TEXT_CLAUSE = """
Restricciones (OBLIGATORIO):
- NO agregues texto nuevo, NO agregues logos, NO agregues marcas de agua.
- NO agregues packaging inventado si no está en la foto.
- NO agregues manos/personas salvo que se habilite explícitamente modelo/persona.
"""

HYPERREALISM_CLAUSE = """
Hiperrealismo fotográfico (OBLIGATORIO):
- Debe parecer 100% una FOTO REAL (no CGI, no render, no ilustración).
- Iluminación físicamente plausible, sombras coherentes y realistas, sin halos alrededor del producto.
- Texturas naturales y nítidas (sin “piel IA”, sin plasticidad rara, sin patrones falsos).
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
- Imagen 2 = vista secundaria del MISMO producto (ej: espalda / suela / etiqueta / otro ángulo).
- Ambas imágenes son el MISMO ítem (no variantes). Deben coincidir: forma, colores, costuras, tipografías, materiales, etiquetas reales.
- Usá Imagen 2 para corregir detalles que Imagen 1 no muestre. NO inventes nada que no esté en ninguna de las dos.
"""

# HERO SET LOCK
HERO_SET_LOCK_CLAUSE = """
CONSISTENCIA DE SET (OBLIGATORIO - PRIORIDAD MÁXIMA):
- Te voy a dar una imagen HERO de referencia del set/escenario.
- Debés replicar EXACTAMENTE el set: fondo, props, superficie, paleta, dirección de luz, intensidad, sombras, atmósfera, hora del día.
- PROHIBIDO: cambiar locación, cambiar materiales del entorno, agregar/quitar props, cambiar el cielo/atardecer, cambiar el tipo de lugar.
- SOLO puede variar: ángulo de cámara, distancia (zoom), encuadre, foco (DOF) y rotación del producto.
"""

# MODEL IDENTITY LOCK
MODEL_IDENTITY_LOCK_CLAUSE = """
CONSISTENCIA DE MODELO (OBLIGATORIO - PRIORIDAD MÁXIMA):
- Te doy una imagen HERO donde aparece el/la modelo (referencia).
- Debe ser EXACTAMENTE la misma persona en TODAS las fotos: mismo rostro, facciones, tono de piel, nariz, labios, mandíbula, cejas, ojos, orejas.
- Mantener también: mismo peinado/longitud/color de pelo, mismo estilo de maquillaje (si hay), misma complexión corporal.
- PROHIBIDO: cambiar edad aparente, cambiar etnia aparente, cambiar forma de cara, “beautify”, cambiar pelo, agregar/quitar barba, cambiar cejas.
- Variaciones permitidas: micro-expresión natural + leve cambio de pose, pero identidad idéntica.
- Si no podés mantener la identidad 100%, preferí NO mostrar la cara (perfil parcial / crop) antes que inventar otra persona.
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
    # guardamos la secundaria con sufijo _2
    for ext in ["png", "jpg", "jpeg", "webp"]:
        p = PRODUCTS_DIR / f"{product_id}_2.{ext}"
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
- prompt_boosters: 4-8 líneas cortas, accionables (ej: "respetar textura X", "mantener costuras", "evitar deformación", etc.).
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

        # mini-sanitizado: asegurar campos
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

# ----------------- Recomendador (lo que hace útil el inputbox) -----------------

def _normalize_txt(s: str) -> str:
    return (s or "").strip().lower()

def _is_apparel(pt: str) -> bool:
    pt = _normalize_txt(pt)
    keys = ["remera", "camisa", "pantalon", "pantalón", "hoodie", "buzo", "ropa", "vestido", "campera", "jersey", "musculosa", "short", "shorts"]
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
        "rustico ": "madera natural, textura cálida, luz natural suave",
        "rústico": "madera natural, textura cálida, luz natural suave",
    }.get(aest, "set limpio, luz suave, sombras reales")

    if _is_bottle(pt):
        extra = "reflejos/vidrio realistas, etiqueta legible sin inventar, sin condensación falsa, sin deformar el vidrio"
    elif _is_shoes(pt):
        extra = "detalle de costuras/mesh, suela visible en una toma, sin deformar la silueta, textura real"
    elif _is_apparel(pt):
        extra = "tela realista, caída natural, costuras nítidas, sin logos inventados, pliegues naturales"
    elif _is_furniture(pt):
        extra = "material realista (tela/cuero), sombras reales en el piso, escala correcta, sin deformaciones"
    else:
        extra = "texturas naturales, sombras coherentes, cero look IA, sin artefactos"

    return f"{aest_base}. {extra}."

def _recommended_config(product_type: str, aesthetic: str) -> Dict[str, Any]:
    pt = _normalize_txt(product_type)
    aest = _normalize_txt(aesthetic) or "minimalista"

    # defaults
    env_type = "studio"
    scene = "white"
    style = "ecommerce"
    lighting = "studio_soft"
    chips: List[str] = []

    # chips por estética
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

    # categoría ajusta set base
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
        env_type = "indoor_real"
        scene = "living_room" if aest in ["minimalista", "clean"] else "jewelry_store"
        lighting = "natural" if aest in ["minimalista", "clean", "rustico"] else "premium"
        style = "instagram_ads"
        chips = list(dict.fromkeys(chips + ["clean"]))
    elif _is_furniture(pt):
        env_type = "indoor_real"
        scene = "living_room"
        lighting = "natural"
        style = "lifestyle"
        chips = list(dict.fromkeys(chips + ["clean"]))

    # clamp scene to allowed set
    if scene not in SCENES_BY_TYPE.get(env_type, set()):
        scene = sorted(list(SCENES_BY_TYPE.get(env_type, {"white"})))[0]

    return {
        "environment": {"type": env_type, "scene": scene, "chips": chips},
        "style": style,
        "lighting": lighting,
        "model_defaults": {
            # NO activamos modelo automáticamente (mejor para no romper)
            "enabled": False,
            "gender": "female",
            "age_range": "25-35",
            "appearance": "",
        },
    }

# ----------------- Prompt builder -----------------

def _build_instruction(req: GenerateFromProductConfigRequest, has_secondary: bool = False) -> str:
    chips_txt = ", ".join([c.strip() for c in req.environment.chips if c.strip()])
    custom = (req.environment.custom_text or "").strip()

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

    scene_text = (getattr(req.environment, "scene_text", "") or "").strip()

    base = f"""
    Contexto de toma:
    - Estilo: {req.style}
    - Iluminación: {req.lighting}
    """

    # ✅ Si hay texto libre, manda eso como fuente de verdad del set
    if scene_text:
        base += f"""
    - ESCENARIO (texto libre, OBLIGATORIO): {scene_text}
    - REGLA: el escenario debe coincidir EXACTAMENTE con el texto libre (no reemplazar por otra cosa similar).
    - REGLA: si el texto libre dice "playa al atardecer", debe haber playa + luz de atardecer (golden hour) de forma inequívoca.
    - REGLA: no convertir el escenario en "gym", "studio", "living room", etc. a menos que el texto libre lo pida.
    """
    else:
        # 🔁 fallback: lo de siempre
        base += f"""
    - Ambiente: {req.environment.type}
    - Escena/fondo: {req.environment.scene}
    """


    if chips_txt:
        base += f"- Elementos/mood: {chips_txt}\n"
    if custom:
        base += f"- Detalles extra: {custom}\n"

    instruction = (
        "INSTRUCCIONES IMPORTANTES:\n"
        + (MULTIVIEW_CLAUSE if has_secondary else "")
        + LOCK_PRODUCT_CLAUSE
        + NO_TEXT_CLAUSE
        + HYPERREALISM_CLAUSE
        + CONSISTENCY_CLAUSE
        + ("\n" + MODEL_IDENTITY_LOCK_CLAUSE if (req.model and req.model.enabled) else "")
        + "\n"
        + base
        + "\n"
        + model_txt
        + "\nResultado: foto publicitaria profesional, hiperrealista, lista para e-commerce."
    )
    return instruction.strip()

def _generate_image_with_prompt(
    product_bytes: bytes,
    mime: str,
    instruction: str,
    secondary_bytes: Optional[bytes] = None,
    secondary_mime: Optional[str] = None,
    hero_ref_bytes: Optional[bytes] = None,
    hero_ref_mime: Optional[str] = None,
) -> Tuple[bytes, str]:
    client = _client()

    contents = [types.Part.from_bytes(data=product_bytes, mime_type=mime)]

    # 2da foto del producto
    if secondary_bytes and secondary_mime:
        contents.append("IMAGEN 2 (vista secundaria del MISMO producto):")
        contents.append(types.Part.from_bytes(data=secondary_bytes, mime_type=secondary_mime))

    # 🔥 ancla visual del set (hero reference)
    if hero_ref_bytes and hero_ref_mime:
        contents.append("REFERENCIA VISUAL DEL SET (HERO):")
        contents.append(types.Part.from_bytes(data=hero_ref_bytes, mime_type=hero_ref_mime))

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
Quiero evaluar 2 cosas:
1) hiperrealismo fotográfico (parece foto real, sin look IA/CGI)
2) producto locked (mismo producto: forma, colores, detalles, etiquetas; sin deformaciones)

Schema:
{
  "photorealism_score": number,
  "product_locked_score": number,
  "issues": [string],
  "verdict": "pass" | "fail"
}

Reglas:
- FAIL si photorealism_score < 85 o product_locked_score < 90.
- Sé estricto con artefactos, halos, bordes raros, texturas falsas, cambios de color.
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
    """
    Evalúa si la persona/modelo es la misma entre HERO y la imagen generada.
    Devuelve JSON con score + verdict.
    """
    try:
        client = _client()
        instruction = """
Devolvé SOLO JSON válido (sin markdown).

Compará la PERSONA/MODELO de la imagen HERO vs la imagen GENERADA.
Quiero evaluar identidad facial: ¿es la MISMA persona?

Schema:
{
  "identity_score": number,
  "issues": [string],
  "verdict": "pass" | "fail"
}

Reglas:
- FAIL si identity_score < 90.
- Sé estricto: si cambian facciones, edad aparente, pelo, cejas, nariz, mandíbula, tono de piel => bajar score.
- Si la cara no se ve (crop/espalda), pero el pelo/rasgos visibles coinciden y no hay contradicción fuerte, podés PASS con score moderado (90-95).
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
    issues_txt = ", ".join(issues[:6]) if isinstance(issues, list) else ""

    reinforcement = f"""
REINTENTO (corregir fallas):
- Si hay cualquier look IA/CGI, hacelo más fotográfico y natural (sin halos, sin texturas falsas).
- Si el producto cambió aunque sea mínimo, volver a dejarlo 100% idéntico al original.
- Si el set/escenario cambió aunque sea mínimo, volver a dejarlo 100% idéntico en todas las fotos generadas.
- Corregir específicamente: {issues_txt or "artefactos / no-foto / cambios de producto"}.
- Mantener MISMA escena/estilo/iluminación seleccionados; NO cambiar el concepto.
"""
    return (instruction + "\n\n" + reinforcement).strip()

# ===================== PACK VARIATIONS =====================

def _variation_hint(i: int) -> str:
    shots = [
        "SHOT: ángulo 3/4 (rotación ~20°). Encuadre MEDIO. Fondo y luz iguales a la HERO. DOF suave.",
        "SHOT: CLOSE-UP detalle (textura/etiqueta/logo/costura). Enfoque muy nítido en el detalle. Fondo y luz iguales.",
        "SHOT: cámara ligeramente más alta (semi top-down). Encuadre más ABIERTO. Mantener mismo fondo y luz.",
        "SHOT: perfil lateral (rotación ~90°). Encuadre MEDIO. Mantener mismo set. Sombra coherente.",
        "SHOT: macro (muy cerca) con bokeh natural (sin look falso). Mantener mismo set.",
        "SHOT: encuadre más ABIERTO que la HERO, más aire alrededor. Misma luz y fondo.",
        "SHOT: encuadre más CERRADO que la HERO, crop distinto. Misma luz y fondo.",
    ]
    return shots[i % len(shots)]

def _build_match_hero_instruction(base_instruction: str, hint: str, index: int) -> str:
    return (
        base_instruction
        + "\n\n"
        + HERO_SET_LOCK_CLAUSE
        + "\n\n"
        + "MODO PACK (OBLIGATORIO):\n"
        + "- La imagen HERO provista define el SET real (fondo/props/luz). Debe ser idéntico.\n"
        + "- NO copies la composición exacta de la HERO.\n"
        + "- Esta toma DEBE ser visualmente distinta: cambiar posición de cámara, ángulo, distancia focal, encuadre y/o foco.\n"
        + "- Prohibido inventar nuevas locaciones: mismo escenario exacto que la HERO.\n"
        + "- Si hay modelo habilitado, debe ser la MISMA persona (mismo rostro/facciones/pelo/piel) en todas.\n"
        + f"- {hint}\n"
        + f"- REGLA: esta es la opción #{index}. Debe verse distinta a la HERO y distinta a las otras opciones.\n"
        + "- Resultado: foto real hiperrealista de un mismo shoot, con variación clara de ángulos y enfoque.\n"
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

    # RECOMENDACIÓN + PREFILL (lo importante)
    prefill = _prefill_custom_text(product_type, aesthetic)
    reco = _recommended_config(product_type, aesthetic)

    # AUTO-DESCRIPCIÓN (lo nuevo, automático)
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

        # esto es lo que el front tiene que mostrar
        "prefill_custom_text": prefill,
        "recommended_config": reco,

        # NUEVO: descripción del producto generada por visión
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

@app.post("/generate-from-product-preset")
def generate_from_product_preset(req: GeneratePresetRequest):
    if req.preset not in PRESETS:
        raise HTTPException(status_code=400, detail="Preset inválido")

    p = _find_product_path(req.product_id)
    product_bytes = p.read_bytes()
    mime = _mime_for_path(p)

    instruction = (
        "INSTRUCCIONES IMPORTANTES:\n"
        + LOCK_PRODUCT_CLAUSE
        + NO_TEXT_CLAUSE
        + HYPERREALISM_CLAUSE
        + CONSISTENCY_CLAUSE
        + "\n"
        + "Preset:\n"
        + PRESETS[req.preset]["prompt"]
        + "\nResultado: foto publicitaria profesional, hiperrealista, lista para e-commerce."
    )

    gen_bytes, out_mime = _generate_image_with_prompt(product_bytes, mime, instruction)
    saved = _save_output(gen_bytes, out_mime)
    return {"ok": True, **saved, "preset": req.preset, "prompt_used": instruction}

@app.post("/generate-from-product-config")
def generate_from_product_config(req: GenerateFromProductConfigRequest):
    if req.environment.scene not in SCENES_BY_TYPE.get(req.environment.type, set()):
        raise HTTPException(status_code=400, detail="Escena inválida para ese environment.type")

    product_path = _find_product_path(req.product_id)
    product_bytes = product_path.read_bytes()
    product_mime = _mime_for_path(product_path)

    sec_bytes, sec_mime = _secondary_bytes(req.product_id)
    has_secondary = bool(sec_bytes and sec_mime)

    instruction = _build_instruction(req, has_secondary=has_secondary)

    gen_bytes, out_mime = _generate_image_with_prompt(product_bytes, product_mime, instruction, sec_bytes, sec_mime)
    qc = _qc_eval(product_bytes, product_mime, gen_bytes, out_mime) or {}

    attempts = 1
    while attempts < 3:
        if not qc:
            break
        if qc.get("verdict") == "pass":
            break
        instruction = _reinforce_for_retry(instruction, qc)
        gen_bytes, out_mime = _generate_image_with_prompt(product_bytes, product_mime, instruction, sec_bytes, sec_mime)
        qc = _qc_eval(product_bytes, product_mime, gen_bytes, out_mime) or qc
        attempts += 1

    saved = _save_output(gen_bytes, out_mime)
    return {"ok": True, **saved, "prompt_used": instruction, "qc": qc, "attempts": attempts}

@app.post("/generate-pack")
def generate_pack(req: GeneratePackRequest):
    n = max(2, min(int(req.n or 5), 10))

    if req.environment.scene not in SCENES_BY_TYPE.get(req.environment.type, set()):
        raise HTTPException(status_code=400, detail="Escena inválida para ese environment.type")

    product_path = _find_product_path(req.product_id)
    product_bytes = product_path.read_bytes()
    product_mime = _mime_for_path(product_path)

    meta = _load_product_meta(req.product_id) or {}
    pt = (meta.get("product_type") or "").strip().lower()

    sec_bytes, sec_mime = _secondary_bytes(req.product_id)
    has_secondary = bool(sec_bytes and sec_mime)

    base_instruction = _build_instruction(
        GenerateFromProductConfigRequest(
            product_id=req.product_id,
            environment=req.environment,
            style=req.style,
            lighting=req.lighting,
            model=req.model,
        ),
        has_secondary=has_secondary
    )

    images = []

    hero_instruction = (
        base_instruction
        + "\n\nHERO (opción #1):\n"
        + "- Esta es la toma principal (pack shot).\n"
        + "- Fondo y luz limpios, composición clara, producto protagonista.\n"
        + "- Foto hiperrealista, sin look IA.\n"
    ).strip()

    gen_bytes, out_mime = _generate_image_with_prompt(
        product_bytes, product_mime, hero_instruction,
        sec_bytes, sec_mime
    )
    hero_bytes = gen_bytes
    hero_mime = out_mime

    saved = _save_output(gen_bytes, out_mime)
    images.append({
        "image_id": saved["image_id"],
        "view_url": saved["view_url"],
        "mime": saved["mime"],
        "index": 1,
        "role": "hero",
        "prompt_used": hero_instruction,
    })

    forced_hint = None
    if has_secondary:
        if _is_apparel(pt):
            forced_hint = "SHOT OBLIGATORIO: VISTA TRASERA (mostrar espalda del producto). Usar Imagen 2 como referencia principal para esta toma."
        elif _is_shoes(pt):
            forced_hint = "SHOT OBLIGIGATORIO: SUELA / PARTE INFERIOR (mostrar suela claramente). Usar Imagen 2 como referencia principal para esta toma."
        elif _is_bottle(pt):
            forced_hint = "SHOT OBLIGATORIO: ETIQUETA / BACK LABEL (mostrar etiqueta posterior o detalle que esté en Imagen 2)."
        else:
            forced_hint = "SHOT OBLIGATORIO: usar la vista de Imagen 2 como base (otro ángulo del mismo producto)."

    for i in range(n - 1):
        hint = forced_hint if (forced_hint and i == 0) else _variation_hint(i)
        instr = _build_match_hero_instruction(base_instruction, hint, i + 2)

        gen_bytes, out_mime = _generate_image_with_prompt(
            product_bytes, product_mime, instr,
            sec_bytes, sec_mime,
            hero_bytes, hero_mime
        )
        qc = _qc_eval(product_bytes, product_mime, gen_bytes, out_mime) or {}
        # model identity QC (solo si hay modelo habilitado en request)
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

            # refuerzo extra si falla identidad
            if req.model and req.model.enabled and model_qc and model_qc.get("verdict") == "fail":
                issues = model_qc.get("issues") if isinstance(model_qc.get("issues"), list) else []
                instr = (instr + "\n\nREINTENTO IDENTIDAD MODELO:\n"
                         + "- La persona debe ser exactamente la misma que en la HERO.\n"
                         + "- Corregir: " + (", ".join(issues[:6]) if issues else "cambios de facciones") + "\n"
                         + "- Mantener set idéntico a HERO.\n").strip()

            gen_bytes, out_mime = _generate_image_with_prompt(
                product_bytes, product_mime, instr,
                sec_bytes, sec_mime,
                hero_bytes, hero_mime
            )

            qc = _qc_eval(product_bytes, product_mime, gen_bytes, out_mime) or qc
            if req.model and req.model.enabled:
                model_qc = _qc_model_identity(hero_bytes, hero_mime, gen_bytes, out_mime) or model_qc

            attempts += 1

        saved = _save_output(gen_bytes, out_mime)
        images.append({
            "image_id": saved["image_id"],
            "view_url": saved["view_url"],
            "mime": saved["mime"],
            "index": i + 2,
            "role": "match",
            "prompt_used": instr,
            "qc": qc,
            "model_qc": model_qc,
            "attempts": attempts,
            "shot_hint": hint,
        })

    return {"ok": True, "n": n, "images": images}
