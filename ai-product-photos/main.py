import os
import uuid
from pathlib import Path
from typing import Optional, List, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
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

# --- Folders ---
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

PRODUCTS_DIR = Path("products")
PRODUCTS_DIR.mkdir(exist_ok=True)

# --- Presets clásicos (opcionales, siguen funcionando) ---
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

# ===================== NUEVO SISTEMA CONFIGURABLE =====================

EnvironmentType = Literal["studio", "indoor_real", "lifestyle", "outdoor"]
LightingType = Literal["studio_soft", "natural", "premium", "dramatic"]
StyleType = Literal["ecommerce", "lifestyle", "advertising", "instagram_ads"]
ChipType = Literal["luxury", "minimal", "modern", "rustic", "clean", "premium"]


class EnvironmentConfig(BaseModel):
    type: EnvironmentType
    scene: str
    chips: List[ChipType] = []
    custom_text: Optional[str] = ""


class ModelConfig(BaseModel):
    enabled: bool = False
    gender: Optional[Literal["female", "male"]] = None
    age_range: Optional[Literal["18-24", "25-35", "36-50", "50+"]] = None
    appearance: Optional[str] = ""


class UploadProductResponse(BaseModel):
    ok: bool
    product_id: str
    view_url: str


class GeneratePresetRequest(BaseModel):
    product_id: str
    preset: str


class GenerateFromProductConfigRequest(BaseModel):
    product_id: str
    environment: EnvironmentConfig
    style: StyleType = "ecommerce"
    lighting: LightingType = "studio_soft"
    model: ModelConfig = ModelConfig(enabled=False)


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


def _mime_for_path(p: Path) -> str:
    ext = p.suffix.lower().replace(".", "")
    return "image/jpeg" if ext in ["jpg", "jpeg"] else f"image/{ext}"


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
        "view_url": f"http://127.0.0.1:8000/image/{image_id}",
    }


def _generate_with_product_bytes(product_bytes: bytes, mime: str, instruction: str) -> dict:
    client = _client()
    resp = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[
            types.Part.from_bytes(data=product_bytes, mime_type=mime),
            instruction,
        ],
    )
    image_bytes, out_mime = _extract_image_bytes(resp)
    return {"ok": True, **_save_output(image_bytes, out_mime)}


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
        "model": {"genders": ["female", "male"], "age_ranges": ["18-24", "25-35", "36-50", "50+"]},
    }


@app.get("/presets")
def list_presets():
    return {"presets": [{"key": k, "title": v["title"]} for k, v in PRESETS.items()]}


@app.post("/upload-product")
def upload_product(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Debe ser imagen")

    # extensión
    ext = (file.filename.split(".")[-1] if file.filename else "").lower()
    if ext not in ["png", "jpg", "jpeg", "webp"]:
        raise HTTPException(status_code=400, detail="Formato no soportado")

    product_id = str(uuid.uuid4())
    path = PRODUCTS_DIR / f"{product_id}.{ext}"
    path.write_bytes(file.file.read())

    return {
        "ok": True,
        "product_id": product_id,
        "view_url": f"http://127.0.0.1:8000/product/{product_id}",
    }


@app.get("/product/{product_id}")
def get_product(product_id: str):
    p = _find_product_path(product_id)
    return Response(p.read_bytes(), media_type=_mime_for_path(p))


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
        "Usá la imagen como referencia principal. "
        "NO deformes el producto. "
        "NO agregues texto ni logos. "
        + PRESETS[req.preset]["prompt"]
    )

    out = _generate_with_product_bytes(product_bytes, mime, instruction)
    out["preset"] = req.preset
    return out


@app.post("/generate-from-product-config")
def generate_from_product_config(req: GenerateFromProductConfigRequest):
    # validación escena vs tipo
    if req.environment.scene not in SCENES_BY_TYPE.get(req.environment.type, set()):
        raise HTTPException(status_code=400, detail="Escena inválida para ese environment.type")

    product_path = _find_product_path(req.product_id)
    product_bytes = product_path.read_bytes()
    mime = _mime_for_path(product_path)

    chips_txt = ", ".join([c.strip() for c in req.environment.chips if c.strip()])
    custom = (req.environment.custom_text or "").strip()

    if req.model and req.model.enabled:
        gender = req.model.gender or "female"
        age = req.model.age_range or "25-35"
        appearance = (req.model.appearance or "").strip()
        model_txt = (
            f"Incluir modelo/persona: sí. Género: {gender}. Edad: {age}. "
            + (f"Apariencia/estilo: {appearance}. " if appearance else "")
            + "La persona NO debe tapar el producto. Presencia sutil si aplica."
        )
    else:
        model_txt = "Incluir modelo/persona: no."

    instruction = (
        "Usá la imagen del producto como referencia principal. "
        "Mantené el producto EXACTAMENTE igual (forma, color, detalles), "
        "sin deformarlo ni inventar texto/logos. "
        "Sin marcas de agua. Sin texto agregado.\n\n"
        f"Estilo: {req.style}. Iluminación: {req.lighting}.\n"
        f"Ambiente: {req.environment.type}. Escena/fondo: {req.environment.scene}.\n"
        + (f"Elementos: {chips_txt}.\n" if chips_txt else "")
        + (f"Detalles extra: {custom}.\n" if custom else "")
        + model_txt
        + "\nFoto publicitaria profesional, alta nitidez."
    )

    out = _generate_with_product_bytes(product_bytes, mime, instruction)
    out["prompt_used"] = instruction
    return out
