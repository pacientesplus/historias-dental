#!/usr/bin/env python3
"""
Publica historias de Instagram automáticamente — Dental Ciudad.

Corre una vez por día desde GitHub Actions:

  1. Mira la carpeta videos/ del repositorio.
  2. Elige 1 a 3 al azar, priorizando los que hace más tiempo que no salen.
  3. Los recorta a 60 s y los pasa a vertical 1080x1920.
  4. Los sube como assets de una Release pública (así tienen URL alcanzable).
  5. Publica cada uno como historia en las cuentas activas.
  6. Anota lo publicado en historial.json para no repetir.

Los tokens llegan por variables de entorno (GitHub Secrets), nunca escritos
en el repositorio.
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

RAIZ = Path(__file__).parent
CARPETA_VIDEOS = RAIZ / "videos"
ARCHIVO_CONFIG = RAIZ / "config.json"
ARCHIVO_HISTORIAL = RAIZ / "historial.json"
CARPETA_TRABAJO = RAIZ / ".trabajo"

GRAPH = "https://graph.instagram.com/v23.0"
TAG_RELEASE = "clips"

EXTENSIONES = {".mp4", ".mov", ".m4v", ".webm", ".avi"}
DURACION_MAX_SEG = 60
TAMANO_MAX_MB = 90          # tope de un asset que Instagram descargue cómodo
TIMEOUT_FFMPEG = 600

# Cuánto espera Instagram para transcodificar antes de que nos rindamos.
INTENTOS_ESTADO = 40
ESPERA_ENTRE_INTENTOS = 6


# ---------------------------------------------------------------------------
# Configuración e historial
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
            print(f"   ⚠ {cuenta['usuario']}: falta el secret {cuenta['token_secret']}")
            continue
        activas.append({**cuenta, "token": token})

    if not activas:
        raise SystemExit("No hay ninguna cuenta activa con token. No hay nada que hacer.")
    return cfg, activas


def cargar_historial():
    if not ARCHIVO_HISTORIAL.exists():
        return {"ultimo_uso": {}, "publicaciones": []}
    with open(ARCHIVO_HISTORIAL, encoding="utf-8") as f:
        return json.load(f)


def guardar_historial(historial):
    # Guardamos solo las últimas 500 publicaciones: alcanza de sobra para
    # auditar y evita que el archivo crezca sin control.
    historial["publicaciones"] = historial["publicaciones"][-500:]
    with open(ARCHIVO_HISTORIAL, "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False, indent=2)


def dias_sin_usar(historial, nombre):
    iso = historial.get("ultimo_uso", {}).get(nombre)
    if not iso:
        return 10_000
    visto = datetime.fromisoformat(iso)
    if visto.tzinfo is None:
        visto = visto.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - visto).days


# ---------------------------------------------------------------------------
# Selección
# ---------------------------------------------------------------------------

def elegir(videos, historial, cantidad, descanso):
    """Elige al azar, pero con memoria: los que hace más que no salen tienen
    más chance. Los publicados hace menos de 'descanso' días quedan afuera,
    salvo que no haya suficientes y haya que completar."""
    if not videos:
        return []

    con_edad = [(v, dias_sin_usar(historial, v.name)) for v in videos]
    descansados = [par for par in con_edad if par[1] >= descanso]

    if len(descansados) >= cantidad:
        pool = descansados
    else:
        con_edad.sort(key=lambda par: par[1], reverse=True)
        pool = con_edad[: max(cantidad * 3, cantidad)]
        print(f"   (banco chico: no alcanzan los descansados, uso los más viejos)")

    opciones = [v for v, _ in pool]
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
# Video
# ---------------------------------------------------------------------------

def duracion(ruta):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(ruta)],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def preparar(entrada, salida):
    """Deja el video como Instagram lo quiere: vertical, hasta 60 s, liviano."""
    dur = duracion(entrada)
    recorte = ["-t", str(DURACION_MAX_SEG)] if dur > DURACION_MAX_SEG else []

    filtro = ("scale=1080:1920:force_original_aspect_ratio=decrease,"
              "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,"
              "setsar=1,fps=30")

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(entrada), *recorte,
         "-vf", filtro,
         "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
         "-preset", "medium", "-crf", "26", "-maxrate", "3M", "-bufsize", "6M",
         "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
         "-movflags", "+faststart",
         str(salida)],
        capture_output=True, check=True, timeout=TIMEOUT_FFMPEG)

    mb = salida.stat().st_size / 1_000_000
    if mb > TAMANO_MAX_MB:
        raise RuntimeError(f"quedó en {mb:.1f} MB, demasiado pesado")
    return mb


def publicar_asset(ruta):
    """Sube el clip a la Release pública y devuelve su URL descargable."""
    repo = os.environ["GITHUB_REPOSITORY"]
    subprocess.run(["gh", "release", "upload", TAG_RELEASE, str(ruta), "--clobber"],
                   check=True, capture_output=True)
    return f"https://github.com/{repo}/releases/download/{TAG_RELEASE}/{ruta.name}"


# ---------------------------------------------------------------------------
# Instagram
# ---------------------------------------------------------------------------

def publicar_historia(cuenta, video_url):
    """Crea el contenedor, espera el transcodificado y publica. Devuelve el id."""
    r = requests.post(f"{GRAPH}/{cuenta['ig_user_id']}/media",
                      data={"media_type": "STORIES",
                            "video_url": video_url,
                            "access_token": cuenta["token"]},
                      timeout=90)
    if not r.ok:
        raise RuntimeError(f"no se pudo crear el contenedor: {r.text[:300]}")
    contenedor = r.json()["id"]

    for _ in range(INTENTOS_ESTADO):
        time.sleep(ESPERA_ENTRE_INTENTOS)
        est = requests.get(f"{GRAPH}/{contenedor}",
                           params={"fields": "status_code,status",
                                   "access_token": cuenta["token"]},
                           timeout=30).json()
        code = est.get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError(f"Instagram rechazó el video: {est.get('status')}")
    else:
        raise TimeoutError("Instagram no terminó de procesar a tiempo")

    r = requests.post(f"{GRAPH}/{cuenta['ig_user_id']}/media_publish",
                      data={"creation_id": contenedor,
                            "access_token": cuenta["token"]},
                      timeout=90)
    if not r.ok:
        raise RuntimeError(f"no se pudo publicar: {r.text[:300]}")
    return r.json()["id"]


# ---------------------------------------------------------------------------

def main():
    print("== Historias Dental Ciudad ==")
    cfg, cuentas = cargar_config()
    historial = cargar_historial()

    videos = sorted(v for v in CARPETA_VIDEOS.iterdir()
                    if v.suffix.lower() in EXTENSIONES)
    if not videos:
        raise SystemExit("La carpeta videos/ está vacía. Nada para publicar.")
    print(f"   {len(videos)} videos en el banco, {len(cuentas)} cuenta(s) activa(s)")

    cantidad = random.randint(cfg["min_por_dia"], min(cfg["max_por_dia"], len(videos)))
    elegidos = elegir(videos, historial, cantidad, cfg["dias_de_descanso"])
    print(f"   Hoy salen {len(elegidos)}:")
    for v in elegidos:
        d = dias_sin_usar(historial, v.name)
        print(f"     · {v.name} ({'nunca usado' if d >= 10_000 else f'hace {d} días'})")

    CARPETA_TRABAJO.mkdir(exist_ok=True)
    hubo_error = False

    for video in elegidos:
        print()
        print(f"-- {video.name}")
        marca = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        clip = CARPETA_TRABAJO / f"historia_{marca}_{random.randint(1000,9999)}.mp4"

        try:
            mb = preparar(video, clip)
            print(f"   preparado: {mb:.1f} MB")
            url = publicar_asset(clip)
        except Exception as e:
            print(f"   ✗ no se pudo preparar: {e}")
            hubo_error = True
            continue

        publicadas = []
        for cuenta in cuentas:
            try:
                post_id = publicar_historia(cuenta, url)
                print(f"   ✓ {cuenta['usuario']} → {post_id}")
                publicadas.append(cuenta["usuario"])
            except Exception as e:
                print(f"   ✗ {cuenta['usuario']}: {e}")
                hubo_error = True

        if publicadas:
            ahora = datetime.now(timezone.utc).isoformat()
            historial.setdefault("ultimo_uso", {})[video.name] = ahora
            historial.setdefault("publicaciones", []).append(
                {"fecha": ahora, "video": video.name, "cuentas": publicadas})

    guardar_historial(historial)
    print()
    print("Listo.")
    # Si algo falló queremos que la corrida quede marcada en rojo en GitHub,
    # para enterarnos sin tener que abrir los registros.
    return 1 if hubo_error else 0


if __name__ == "__main__":
    sys.exit(main())
