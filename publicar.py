#!/usr/bin/env python3
"""
Publica historias de Instagram automaticamente - Dental Ciudad.

Corre una vez por dia desde GitHub Actions:

  1. Lee la carpeta de Google Drive donde Eduardo tira fotos y videos.
  2. Elige 1 a 3 al azar, priorizando los que hace mas tiempo que no salen.
  3. Los deja como Instagram los quiere: vertical 1080x1920, videos de
     hasta 60 s, fotos en JPG (convierte HEIC del iPhone y MOV sin drama).
  4. Los sube como assets de una Release publica, que es la unica forma
     de darle a Instagram una direccion desde donde descargarlos.
  5. Publica cada uno como historia en las cuentas activas.
  6. Anota lo publicado para no repetir.

Ninguna credencial vive en este archivo: llegan por variables de entorno
(GitHub Secrets).
"""

import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image
import pillow_heif

pillow_heif.register_heif_opener()

RAIZ = Path(__file__).parent
ARCHIVO_CONFIG = RAIZ / "config.json"
ARCHIVO_HISTORIAL = RAIZ / "historial.json"
CARPETA_TRABAJO = RAIZ / ".trabajo"

GRAPH = "https://graph.instagram.com/v23.0"
DRIVE = "https://www.googleapis.com/drive/v3/files"
TAG_RELEASE = "clips"

DURACION_MAX_SEG = 60
TIMEOUT_FFMPEG = 600

# Instagram no acepta fotos de mas de 8 MB. Dejamos margen.
FOTO_MAX_MB = 7
VIDEO_MAX_MB = 90

# Archivos gigantes ni los bajamos: procesarlos tarda mucho y casi nunca
# son material de historia.
ORIGEN_MAX_MB = 300

INTENTOS_ESTADO = 40
ESPERA_ENTRE_INTENTOS = 6


# ---------------------------------------------------------------------------
# Configuracion e historial
# ---------------------------------------------------------------------------

def cargar_config():
    with open(ARCHIVO_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)

    activas = []
    for cuenta in cfg["cuentas"]:
        if not cuenta.get("activa"):
            print(f"   {cuenta['usuario']}: desactivada, se saltea")
            continue
        token = os.environ.get(cuenta["token_secret"], "").strip()
        if not token:
            print(f"   AVISO {cuenta['usuario']}: falta el secret {cuenta['token_secret']}")
            continue
        activas.append({**cuenta, "token": token})

    if not activas:
        raise SystemExit("No hay ninguna cuenta activa con token. Nada que hacer.")
    return cfg, activas


def cargar_historial():
    if not ARCHIVO_HISTORIAL.exists():
        return {"ultimo_uso": {}, "publicaciones": []}
    with open(ARCHIVO_HISTORIAL, encoding="utf-8") as f:
        return json.load(f)


def guardar_historial(historial):
    historial["publicaciones"] = historial["publicaciones"][-500:]
    with open(ARCHIVO_HISTORIAL, "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False, indent=2)


def dias_sin_usar(historial, file_id):
    iso = historial.get("ultimo_uso", {}).get(file_id)
    if not iso:
        return 10_000
    visto = datetime.fromisoformat(iso)
    if visto.tzinfo is None:
        visto = visto.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - visto).days


# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------

def listar_drive(carpeta_id, api_key):
    """Devuelve todas las fotos y videos de la carpeta.

    Pagina hasta terminar: si algun dia hay 500 archivos, los trae todos.
    """
    items, token = [], None
    while True:
        params = {
            "q": f"'{carpeta_id}' in parents and trashed=false",
            "fields": "nextPageToken,files(id,name,mimeType,size)",
            "pageSize": 1000,
            "key": api_key,
        }
        if token:
            params["pageToken"] = token
        r = requests.get(DRIVE, params=params, timeout=60)
        if not r.ok:
            raise RuntimeError(f"Drive no responde: {r.status_code} {r.text[:300]}")
        datos = r.json()
        items.extend(datos.get("files", []))
        token = datos.get("nextPageToken")
        if not token:
            break

    utiles, vistos, repetidos = [], set(), 0
    for f in items:
        tipo = f.get("mimeType", "")
        if not (tipo.startswith("video/") or tipo.startswith("image/")):
            continue
        mb = int(f.get("size") or 0) / 1_000_000
        if mb > ORIGEN_MAX_MB:
            print(f"   (salteo {f['name']}: {mb:.0f} MB, demasiado grande)")
            continue

        # Mismo nombre y mismo peso = es el mismo archivo subido dos veces.
        # Nos quedamos con uno solo, asi no tiene doble chance de salir.
        huella = (f["name"].lower(), f.get("size"))
        if huella in vistos:
            repetidos += 1
            continue
        vistos.add(huella)

        f["es_video"] = tipo.startswith("video/")
        utiles.append(f)

    if repetidos:
        print(f"   ({repetidos} repetidos ignorados)")
    return utiles


def bajar_de_drive(file_id, destino, api_key):
    r = requests.get(DRIVE + f"/{file_id}",
                     params={"alt": "media", "key": api_key},
                     timeout=300, stream=True)
    if not r.ok:
        raise RuntimeError(f"no se pudo bajar: {r.status_code} {r.text[:200]}")
    with open(destino, "wb") as f:
        for trozo in r.iter_content(chunk_size=1 << 20):
            f.write(trozo)
    return destino


# ---------------------------------------------------------------------------
# Preparacion del material
# ---------------------------------------------------------------------------

def duracion(ruta):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(ruta)],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def preparar_video(entrada, salida):
    """Vertical 1080x1920, hasta 60 s, liviano. Sirve igual para MOV."""
    salida = Path(salida)
    dur = duracion(entrada)
    recorte = ["-t", str(DURACION_MAX_SEG)] if dur > DURACION_MAX_SEG else []

    filtro = ("scale=1080:1920:force_original_aspect_ratio=decrease,"
              "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,"
              "setsar=1,fps=30")

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(entrada), *recorte,
         "-vf", filtro,
         "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
         "-preset", "veryfast", "-crf", "26", "-maxrate", "3M", "-bufsize", "6M",
         "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
         "-movflags", "+faststart",
         str(salida)],
        capture_output=True, check=True, timeout=TIMEOUT_FFMPEG)

    mb = salida.stat().st_size / 1_000_000
    if mb > VIDEO_MAX_MB:
        raise RuntimeError(f"el video quedo en {mb:.1f} MB, demasiado pesado")
    return mb


def preparar_foto(entrada, salida):
    """JPG vertical 1080x1920 con fondo negro, respetando la proporcion.

    Entiende HEIC (el formato del iPhone), que Instagram rechaza tal cual.
    """
    salida = Path(salida)
    with Image.open(entrada) as img:
        img = img.convert("RGB")
        lienzo = Image.new("RGB", (1080, 1920), (0, 0, 0))
        copia = img.copy()
        copia.thumbnail((1080, 1920), Image.LANCZOS)
        lienzo.paste(copia, ((1080 - copia.width) // 2,
                             (1920 - copia.height) // 2))

        calidad = 90
        while calidad >= 55:
            lienzo.save(salida, "JPEG", quality=calidad, optimize=True)
            mb = salida.stat().st_size / 1_000_000
            if mb <= FOTO_MAX_MB:
                return mb
            calidad -= 10
    raise RuntimeError("no se pudo dejar la foto por debajo del limite de peso")


# ---------------------------------------------------------------------------
# Publicacion
# ---------------------------------------------------------------------------

def subir_asset(ruta):
    """Sube el archivo a la Release publica y devuelve su direccion."""
    repo = os.environ["GITHUB_REPOSITORY"]
    subprocess.run(["gh", "release", "upload", TAG_RELEASE, str(ruta), "--clobber"],
                   check=True, capture_output=True)
    return f"https://github.com/{repo}/releases/download/{TAG_RELEASE}/{ruta.name}"


def publicar_historia(cuenta, url, es_video):
    """Crea el contenedor, espera a que Instagram lo procese y lo publica."""
    datos = {"media_type": "STORIES", "access_token": cuenta["token"]}
    datos["video_url" if es_video else "image_url"] = url

    r = requests.post(f"{GRAPH}/{cuenta['ig_user_id']}/media", data=datos, timeout=90)
    if not r.ok:
        raise RuntimeError(f"no se pudo crear el contenedor: {r.text[:300]}")
    contenedor = r.json()["id"]

    # Las fotos suelen estar listas enseguida; los videos tardan.
    for _ in range(INTENTOS_ESTADO):
        time.sleep(ESPERA_ENTRE_INTENTOS if es_video else 2)
        est = requests.get(f"{GRAPH}/{contenedor}",
                           params={"fields": "status_code,status",
                                   "access_token": cuenta["token"]},
                           timeout=30).json()
        code = est.get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError(f"Instagram lo rechazo: {est.get('status')}")
    else:
        raise TimeoutError("Instagram no termino de procesar a tiempo")

    r = requests.post(f"{GRAPH}/{cuenta['ig_user_id']}/media_publish",
                      data={"creation_id": contenedor,
                            "access_token": cuenta["token"]},
                      timeout=90)
    if not r.ok:
        raise RuntimeError(f"no se pudo publicar: {r.text[:300]}")
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Seleccion
# ---------------------------------------------------------------------------

def elegir(archivos, historial, cantidad, descanso):
    """Al azar, pero con memoria: los que hace mas que no salen pesan mas.
    Los usados hace menos de "descanso" dias quedan afuera, salvo que no
    alcancen y haya que completar con los mas viejos."""
    if not archivos:
        return []

    con_edad = [(a, dias_sin_usar(historial, a["id"])) for a in archivos]
    descansados = [par for par in con_edad if par[1] >= descanso]

    if len(descansados) >= cantidad:
        pool = descansados
    else:
        con_edad.sort(key=lambda par: par[1], reverse=True)
        pool = con_edad[: max(cantidad * 3, cantidad)]
        print("   (banco chico: completo con los mas viejos)")

    opciones = [a for a, _ in pool]
    pesos = [min(d, 365) + 1 for _, d in pool]

    elegidos = []
    for _ in range(min(cantidad, len(opciones))):
        pick = random.choices(opciones, weights=pesos, k=1)[0]
        i = opciones.index(pick)
        opciones.pop(i)
        pesos.pop(i)
        elegidos.append(pick)
    return elegidos


# ---------------------------------------------------------------------------

def main():
    print("== Historias Dental Ciudad ==")
    cfg, cuentas = cargar_config()
    historial = cargar_historial()

    api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Falta el secret GOOGLE_API_KEY.")

    archivos = listar_drive(cfg["carpeta_drive"], api_key)
    if not archivos:
        raise SystemExit("La carpeta de Drive no tiene fotos ni videos.")

    videos = sum(1 for a in archivos if a["es_video"])
    print(f"   {len(archivos)} archivos en Drive "
          f"({videos} videos, {len(archivos) - videos} fotos), "
          f"{len(cuentas)} cuenta(s) activa(s)")

    tope = min(cfg["max_por_dia"], len(archivos))
    cantidad = random.randint(min(cfg["min_por_dia"], tope), tope)
    elegidos = elegir(archivos, historial, cantidad, cfg["dias_de_descanso"])

    print(f"   Hoy salen {len(elegidos)}:")
    for a in elegidos:
        d = dias_sin_usar(historial, a["id"])
        cuando = "nunca usado" if d >= 10_000 else f"hace {d} dias"
        print(f"     - {a['name'][:60]} ({'video' if a['es_video'] else 'foto'}, {cuando})")

    CARPETA_TRABAJO.mkdir(exist_ok=True)
    hubo_error = False

    for archivo in elegidos:
        print()
        print(f"-- {archivo['name'][:70]}")
        marca = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        sufijo = random.randint(1000, 9999)
        crudo = CARPETA_TRABAJO / f"crudo_{marca}_{sufijo}"
        es_video = archivo["es_video"]
        listo = CARPETA_TRABAJO / (f"historia_{marca}_{sufijo}"
                                   + (".mp4" if es_video else ".jpg"))

        try:
            bajar_de_drive(archivo["id"], crudo, api_key)
            if es_video:
                mb = preparar_video(crudo, listo)
            else:
                mb = preparar_foto(crudo, listo)
            print(f"   preparado: {mb:.1f} MB")
            url = subir_asset(listo)
        except Exception as e:
            print(f"   FALLO al preparar: {e}")
            hubo_error = True
            continue

        publicadas = []
        for cuenta in cuentas:
            try:
                post_id = publicar_historia(cuenta, url, es_video)
                print(f"   OK {cuenta['usuario']} -> {post_id}")
                publicadas.append(cuenta["usuario"])
            except Exception as e:
                print(f"   FALLO {cuenta['usuario']}: {e}")
                hubo_error = True

        if publicadas:
            ahora = datetime.now(timezone.utc).isoformat()
            historial.setdefault("ultimo_uso", {})[archivo["id"]] = ahora
            historial.setdefault("publicaciones", []).append(
                {"fecha": ahora, "archivo": archivo["name"],
                 "tipo": "video" if es_video else "foto",
                 "cuentas": publicadas})

    guardar_historial(historial)
    print()
    print("Listo.")
    return 1 if hubo_error else 0


if __name__ == "__main__":
    sys.exit(main())
