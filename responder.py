#!/usr/bin/env python3
"""
Responde comentarios de Instagram y Facebook - Dental Ciudad.

Corre cada tanto desde GitHub Actions:

  1. Busca las publicaciones recientes de las 3 cuentas de Instagram
     y de las 3 paginas de Facebook.
  2. Junta los comentarios nuevos (los de las ultimas horas, que no
     sean nuestros y que no hayamos contestado antes).
  3. Le pide a Gemini que decida si vale la pena contestar y, si si,
     que redacte la respuesta siguiendo el guion de instrucciones.txt.
  4. Publica la respuesta abajo del comentario y, si esta habilitado,
     manda tambien el mensaje privado a esa misma persona.
  5. Anota lo hecho para no contestar dos veces.

MODO PRUEBA: mientras bot.json diga "modo_prueba": true, nada de esto
se publica. Se escribe en el registro lo que se HABRIA contestado.

Ninguna credencial vive en este archivo: llegan por variables de
entorno (GitHub Secrets).
"""

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

RAIZ = Path(__file__).parent
ARCHIVO_CONFIG = RAIZ / "bot.json"
ARCHIVO_GUION = RAIZ / "instrucciones.txt"
ARCHIVO_ESTADO = RAIZ / "respondidos.json"

IGGRAPH = "https://graph.instagram.com/v23.0"
FBGRAPH = "https://graph.facebook.com/v23.0"
GEMINI = ("https://generativelanguage.googleapis.com/v1beta/models/"
          "gemini-2.5-flash:generateContent")

TIMEOUT = 60
MAX_ESTADO = 5000


# ---------------------------------------------------------------------------
# Configuracion y memoria
# ---------------------------------------------------------------------------

def cargar_config():
    with open(ARCHIVO_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)

    activas = []
    for cuenta in cfg["cuentas"]:
        if not cuenta.get("activa"):
            continue

        ig = os.environ.get(cuenta["token_secret"], "").strip()
        fb_cfg = cuenta.get("pagina_fb") or {}
        fb = os.environ.get(fb_cfg.get("token_secret", ""), "").strip()

        if not ig and not fb:
            print(f"   AVISO {cuenta['usuario']}: sin tokens, se saltea")
            continue

        activas.append({**cuenta, "token_ig": ig or None, "token_fb": fb or None})

    if not activas:
        raise SystemExit("No hay ninguna cuenta con token. Nada que hacer.")
    return cfg, activas


def cargar_estado():
    if not ARCHIVO_ESTADO.exists():
        return {"contestados": [], "para_revisar": []}
    with open(ARCHIVO_ESTADO, encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("contestados", [])
    d.setdefault("para_revisar", [])
    return d


def guardar_estado(estado):
    estado["contestados"] = estado["contestados"][-MAX_ESTADO:]
    estado["para_revisar"] = estado["para_revisar"][-200:]
    with open(ARCHIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------

def limpiar(texto):
    """Sin acentos y en minuscula, para comparar sin sorpresas."""
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.lower()


def tiene_palabra_prohibida(texto, lista):
    plano = limpiar(texto)
    return next((p for p in lista if limpiar(p) in plano), None)


def vale_la_pena(texto):
    """Filtra comentarios que no piden nada: emojis sueltos, arrobas, 'lindo'."""
    if not texto:
        return False
    # Sacamos arrobas y hashtags; si no queda casi nada, no es una consulta.
    resto = re.sub(r"[@#]\w+", "", texto)
    letras = re.sub(r"[^0-9a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]", "", resto)
    return len(letras) >= 6


def elegir_sede(texto, cfg, cuenta):
    plano = limpiar(texto)
    for sede, pistas in cfg.get("pistas_de_sede", {}).items():
        if any(limpiar(p) in plano for p in pistas):
            return sede
    return cuenta.get("sede_por_defecto", "microcentro")


def reciente(iso, horas):
    if not iso:
        return True
    try:
        # Facebook manda +0000, Instagram tambien.
        t = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        try:
            t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            return True
    return t >= datetime.now(timezone.utc) - timedelta(hours=horas)


# ---------------------------------------------------------------------------
# Lectura de comentarios
# ---------------------------------------------------------------------------

def pedir(url, params):
    r = requests.get(url, params=params, timeout=TIMEOUT)
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.text[:250]}")
    return r.json()


def comentarios_instagram(cuenta, cuantas, horas, propios):
    """Comentarios recientes de las ultimas publicaciones de la cuenta."""
    salida = []
    medios = pedir(f"{IGGRAPH}/{cuenta['ig_user_id']}/media",
                   {"fields": "id,caption,timestamp", "limit": cuantas,
                    "access_token": cuenta["token_ig"]}).get("data", [])
    print(f"   {cuenta['usuario']}: {len(medios)} publicaciones")

    for m in medios:
        try:
            coms = pedir(f"{IGGRAPH}/{m['id']}/comments",
                         {"fields": "id,text,username,timestamp",
                          "limit": 50,
                          "access_token": cuenta["token_ig"]}).get("data", [])
        except Exception as e:
            print(f"   (no pude leer comentarios de {m['id']}: {e})")
            continue

        for c in coms:
            # Las tres cuentas se comentan entre ellas: ninguna se responde
            # a si misma ni a sus hermanas.
            if (c.get("username") or "").lower() in propios:
                continue
            if not reciente(c.get("timestamp"), horas):
                continue
            salida.append({
                "red": "instagram",
                "cuenta": cuenta["usuario"],
                "comentario_id": c["id"],
                "texto": c.get("text", ""),
                "quien": c.get("username", "?"),
                "publicacion": (m.get("caption") or "")[:300],
            })
    return salida


def comentarios_facebook(cuenta, cuantas, horas, propios):
    pagina = cuenta["pagina_fb"]
    salida = []
    posts = pedir(f"{FBGRAPH}/{pagina['page_id']}/posts",
                  {"fields": "id,message,created_time", "limit": cuantas,
                   "access_token": cuenta["token_fb"]}).get("data", [])
    print(f"   {pagina['nombre']}: {len(posts)} publicaciones")

    for p in posts:
        try:
            coms = pedir(f"{FBGRAPH}/{p['id']}/comments",
                         {"fields": "id,message,from,created_time",
                          "limit": 50, "filter": "toplevel",
                          "access_token": cuenta["token_fb"]}).get("data", [])
        except Exception as e:
            print(f"   (no pude leer comentarios de {p['id']}: {e})")
            continue

        for c in coms:
            quien = (c.get("from") or {})
            if (quien.get("id") in propios
                    or limpiar(quien.get("name", "")) in propios):
                continue  # es nuestro o de una pagina hermana
            if not reciente(c.get("created_time"), horas):
                continue
            salida.append({
                "red": "facebook",
                "cuenta": pagina["nombre"],
                "comentario_id": c["id"],
                "texto": c.get("message", ""),
                "quien": quien.get("name", "?"),
                "publicacion": (p.get("message") or "")[:300],
            })
    return salida


# ---------------------------------------------------------------------------
# Redaccion con Gemini
# ---------------------------------------------------------------------------

# En los comentarios de Instagram los links no son tocables: quedan como
# texto muerto. En los privados de Instagram y en todo Facebook si andan.
REGLA_INSTAGRAM = """=== DONDE VA EL LINK (IMPORTANTE) ===

Esto es un comentario de Instagram. En los comentarios de Instagram los links
NO se pueden tocar: quedan como texto muerto y encima queda mal.

- En la respuesta publica NO pongas ningun link ni ninguna direccion web.
  Contesta lo que se pueda e invitala a escribir por privado, o deci que le
  escribis vos por privado. Escribilo natural, no siempre con las mismas
  palabras.
- En el mensaje privado SI va el link, completo y tal cual:
  {link}"""

REGLA_FACEBOOK = """=== DONDE VA EL LINK ===

Esto es Facebook, donde los links si funcionan.

- En la respuesta publica pone el link completo y tal cual: {link}
- En el mensaje privado tambien va el mismo link.
- Nunca lo acortes ni lo adornes."""

FORMATO = """

Respondes SIEMPRE con un JSON, sin nada alrededor, con esta forma:
{"responder": true o false, "motivo": "en pocas palabras por que", "texto": "la respuesta publica, o cadena vacia si responder es false", "privado": "el mensaje para mandarle por privado a esa misma persona, un poco mas largo que el publico"}"""


def cargar_guion():
    """El guion vive en instrucciones.txt para que se pueda editar sin tocar
    codigo ni preocuparse por comas ni comillas."""
    with open(ARCHIVO_GUION, encoding="utf-8") as f:
        return f.read()


def armar_instrucciones(guion, whatsapp, sede, red):
    link = whatsapp[sede]
    regla = (REGLA_INSTAGRAM if red == "instagram" else REGLA_FACEBOOK)
    texto = guion.replace("{REGLA_DE_LINKS}", regla.format(link=link))
    if "{REGLA_DE_LINKS}" in guion:
        return texto + FORMATO
    # Si alguien borro la marca del archivo, la agregamos igual al final.
    return texto + "\n\n" + regla.format(link=link) + FORMATO


def redactar(comentario, instrucciones, api_key):
    cuerpo = {
        "systemInstruction": {"parts": [{"text": instrucciones}]},
        "contents": [{"role": "user", "parts": [{"text":
            f"Publicacion: {comentario['publicacion']}\n"
            f"Comentario de @{comentario['quien']}: {comentario['texto']}"}]}],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 500,
            "responseMimeType": "application/json",
        },
    }
    r = requests.post(GEMINI, params={"key": api_key}, json=cuerpo, timeout=TIMEOUT)
    if not r.ok:
        raise RuntimeError(f"Gemini: {r.status_code} {r.text[:250]}")

    datos = r.json()
    try:
        crudo = datos["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Gemini contesto raro: {json.dumps(datos)[:250]}")

    d = json.loads(crudo)
    return {
        "responder": bool(d.get("responder")),
        "motivo": (d.get("motivo") or "")[:120],
        "texto": (d.get("texto") or "").strip(),
        "privado": (d.get("privado") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Publicacion
# ---------------------------------------------------------------------------

def responder_publico(com, cuenta, texto):
    if com["red"] == "instagram":
        url = f"{IGGRAPH}/{com['comentario_id']}/replies"
        token = cuenta["token_ig"]
    else:
        url = f"{FBGRAPH}/{com['comentario_id']}/comments"
        token = cuenta["token_fb"]

    r = requests.post(url, data={"message": texto, "access_token": token},
                      timeout=TIMEOUT)
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.text[:250]}")
    return r.json().get("id")


def responder_privado(com, cuenta, texto):
    """La 'respuesta privada' de Meta: un mensaje al que comento.

    Solo se puede una vez por comentario y dentro de los 7 dias.
    """
    if com["red"] == "instagram":
        r = requests.post(
            f"{IGGRAPH}/{cuenta['ig_user_id']}/messages",
            json={"recipient": {"comment_id": com["comentario_id"]},
                  "message": {"text": texto}},
            params={"access_token": cuenta["token_ig"]}, timeout=TIMEOUT)
    else:
        r = requests.post(
            f"{FBGRAPH}/{com['comentario_id']}/private_replies",
            data={"message": texto, "access_token": cuenta["token_fb"]},
            timeout=TIMEOUT)

    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.text[:250]}")
    return r.json().get("id") or "ok"


# ---------------------------------------------------------------------------

def main():
    print("== Bot de comentarios Dental Ciudad ==")
    cfg, cuentas = cargar_config()
    guion = cargar_guion()
    estado = cargar_estado()
    ya = set(estado["contestados"])

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Falta el secret GEMINI_API_KEY.")

    prueba = cfg.get("modo_prueba", True)
    privado_activo = cfg.get("responder_privado", False)
    horas = cfg.get("horas_para_atras", 24)
    cuantas = cfg.get("publicaciones_a_revisar", 12)
    tope = cfg.get("max_respuestas_por_corrida", 15)
    prohibidas = cfg.get("no_responder_si_dice", [])

    if prueba:
        print("   MODO PRUEBA: no se publica nada, solo se muestra.")
    print(f"   Mirando las ultimas {cuantas} publicaciones, {horas} h para atras.")

    # Todo lo que somos nosotros: las tres cuentas y las tres paginas.
    # Sirve para no contestarnos entre nosotros mismos.
    propios = set()
    for c in cfg["cuentas"]:
        propios.add(c["usuario"].lower())
        propios.add(c["ig_user_id"])
        fb = c.get("pagina_fb") or {}
        if fb:
            propios.add(fb["page_id"])
            propios.add(limpiar(fb.get("nombre", "")))

    # --- juntar
    pendientes = []
    for cuenta in cuentas:
        if cuenta["token_ig"]:
            try:
                pendientes += comentarios_instagram(cuenta, cuantas, horas, propios)
            except Exception as e:
                print(f"   FALLO leyendo instagram {cuenta['usuario']}: {e}")
        if cuenta["token_fb"] and cuenta.get("pagina_fb"):
            try:
                pendientes += comentarios_facebook(cuenta, cuantas, horas, propios)
            except Exception as e:
                print(f"   FALLO leyendo facebook {cuenta['pagina_fb']['nombre']}: {e}")

    por_usuario = {c["usuario"]: c for c in cuentas}
    por_pagina = {c["pagina_fb"]["nombre"]: c for c in cuentas if c.get("pagina_fb")}

    print(f"   {len(pendientes)} comentarios en el periodo")

    hechos = saltados = marcados = errores = 0

    for com in pendientes:
        if hechos >= tope:
            print("   (llegue al tope de respuestas por corrida)")
            break
        if com["comentario_id"] in ya:
            continue

        cuenta = por_usuario.get(com["cuenta"]) or por_pagina.get(com["cuenta"])
        if not cuenta:
            continue

        etiqueta = f"{com['red']}/{com['cuenta']} @{com['quien']}"
        texto = com["texto"]

        # --- filtros que no dependen de la IA
        if not vale_la_pena(texto):
            saltados += 1
            ya.add(com["comentario_id"])
            estado["contestados"].append(com["comentario_id"])
            continue

        mala = tiene_palabra_prohibida(texto, prohibidas)
        if mala:
            marcados += 1
            print(f"   MIRALO VOS  {etiqueta}: \"{texto[:90]}\"  (dice '{mala}')")
            estado["para_revisar"].append({
                "cuando": datetime.now(timezone.utc).isoformat(),
                "donde": etiqueta, "texto": texto[:400], "motivo": f"dice '{mala}'"})
            ya.add(com["comentario_id"])
            estado["contestados"].append(com["comentario_id"])
            continue

        # --- redaccion
        sede = elegir_sede(texto + " " + com["publicacion"], cfg, cuenta)
        try:
            r = redactar(com, armar_instrucciones(guion, cfg["whatsapp"], sede,
                                                  com["red"]), api_key)
        except Exception as e:
            print(f"   FALLO redactando para {etiqueta}: {e}")
            errores += 1
            continue

        if not r["responder"] or not r["texto"]:
            saltados += 1
            print(f"   paso    {etiqueta}: \"{texto[:60]}\"  ({r['motivo']})")
            ya.add(com["comentario_id"])
            estado["contestados"].append(com["comentario_id"])
            continue

        print()
        print(f"   {etiqueta} ({sede})")
        print(f"     dijo:      {texto[:160]}")
        print(f"     responde:  {r['texto']}")
        if r["privado"]:
            print(f"     privado:   {r['privado'][:300]}")

        if prueba:
            hechos += 1
            continue

        try:
            responder_publico(com, cuenta, r["texto"])
            print("     -> publicado")
            ya.add(com["comentario_id"])
            estado["contestados"].append(com["comentario_id"])
            hechos += 1
        except Exception as e:
            print(f"     -> FALLO al publicar: {e}")
            errores += 1
            continue

        if privado_activo and r["privado"]:
            try:
                responder_privado(com, cuenta, r["privado"])
                print("     -> privado enviado")
            except Exception as e:
                print(f"     -> el privado no salio: {e}")

    if not prueba:
        guardar_estado(estado)

    print()
    print(f"Resumen: {hechos} respuestas, {saltados} sin responder, "
          f"{marcados} para que mires vos, {errores} errores.")
    if prueba:
        print("Era una prueba: no se publico ni se guardo nada.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
