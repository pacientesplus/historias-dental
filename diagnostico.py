#!/usr/bin/env python3
"""
Diagnostico de comentarios - Dental Ciudad.

No forma parte de la automatizacion. Se corre a mano para contestar una
sola pregunta: que nos deja hacer Meta hoy con los comentarios.

Trabaja sobre UNA sola cuenta (la primera activa de bot.json) y sobre su
publicacion mas reciente. Prueba, en orden:

  1. Leer los comentarios de esa publicacion.
  2. Escribir un comentario nuevo ahi.
  3. Volver a leer, para ver si aparece el que acabamos de escribir.
  4. Responderle a ese comentario.
  5. Lo mismo del lado de Facebook.

Cada paso dice OK o el error exacto que devolvio Meta. Al final imprime
los identificadores de lo que haya creado, para poder borrarlo a mano.
"""

import json
import os
import sys
from pathlib import Path

import requests

RAIZ = Path(__file__).parent
IGGRAPH = "https://graph.instagram.com/v23.0"
FBGRAPH = "https://graph.facebook.com/v23.0"
TIMEOUT = 60

TEXTO = "prueba automatica, se borra en un rato"
TEXTO_RESPUESTA = "prueba automatica de respuesta, se borra en un rato"

creados = []


def contar(r):
    """Devuelve (ok, detalle) sin exponer nunca el token."""
    if r.ok:
        return True, r.json()
    try:
        e = r.json().get("error", {})
        return False, f"{r.status_code} ({e.get('code')}) {e.get('message')}"
    except Exception:
        return False, f"{r.status_code} {r.text[:200]}"


def paso(titulo):
    print()
    print("-" * 70)
    print(titulo)
    print("-" * 70)


def diagnostico_instagram(cuenta, token):
    paso(f"INSTAGRAM  @{cuenta['usuario']}")

    r = requests.get(f"{IGGRAPH}/{cuenta['ig_user_id']}/media",
                     params={"fields": "id,caption,timestamp,permalink",
                             "limit": 3, "access_token": token}, timeout=TIMEOUT)
    ok, d = contar(r)
    if not ok:
        print(f"   No pude listar publicaciones: {d}")
        return
    medios = d.get("data", [])
    if not medios:
        print("   La cuenta no tiene publicaciones.")
        return

    m = medios[0]
    print(f"   Publicacion mas reciente: {m['id']}")
    print(f"   {m.get('permalink', '(sin link)')}")

    # 1. leer
    r = requests.get(f"{IGGRAPH}/{m['id']}/comments",
                     params={"fields": "id,text,username,timestamp",
                             "limit": 50, "access_token": token}, timeout=TIMEOUT)
    ok, d = contar(r)
    if ok:
        coms = d.get("data", [])
        print(f"   1. LEER  -> OK, devuelve {len(coms)} comentarios")
        for c in coms[:5]:
            print(f"        @{c.get('username')}: {(c.get('text') or '')[:60]}")
    else:
        print(f"   1. LEER  -> FALLA: {d}")

    # 2. escribir
    r = requests.post(f"{IGGRAPH}/{m['id']}/comments",
                      data={"message": TEXTO, "access_token": token},
                      timeout=TIMEOUT)
    ok, d = contar(r)
    nuevo = None
    if ok:
        nuevo = d.get("id")
        creados.append(("instagram", nuevo))
        print(f"   2. ESCRIBIR COMENTARIO -> OK, id {nuevo}")
    else:
        print(f"   2. ESCRIBIR COMENTARIO -> FALLA: {d}")

    # 3. releer
    r = requests.get(f"{IGGRAPH}/{m['id']}/comments",
                     params={"fields": "id,text,username", "limit": 50,
                             "access_token": token}, timeout=TIMEOUT)
    ok, d = contar(r)
    if ok:
        coms = d.get("data", [])
        visto = any(c.get("id") == nuevo for c in coms) if nuevo else False
        print(f"   3. RELEER -> OK, devuelve {len(coms)} comentarios"
              f"{'  (el nuestro aparece)' if visto else ''}")
    else:
        print(f"   3. RELEER -> FALLA: {d}")

    # 4. responder
    if nuevo:
        r = requests.post(f"{IGGRAPH}/{nuevo}/replies",
                          data={"message": TEXTO_RESPUESTA, "access_token": token},
                          timeout=TIMEOUT)
        ok, d = contar(r)
        if ok:
            hijo = d.get("id")
            creados.append(("instagram", hijo))
            print(f"   4. RESPONDER -> OK, id {hijo}")
        else:
            print(f"   4. RESPONDER -> FALLA: {d}")
    else:
        print("   4. RESPONDER -> salteado (no hay comentario propio para responder)")


def diagnostico_facebook(pagina, token):
    paso(f"FACEBOOK  {pagina['nombre']}")

    r = requests.get(f"{FBGRAPH}/{pagina['page_id']}/posts",
                     params={"fields": "id,message,created_time,permalink_url",
                             "limit": 3, "access_token": token}, timeout=TIMEOUT)
    ok, d = contar(r)
    if not ok:
        print(f"   No pude listar publicaciones: {d}")
        return
    posts = d.get("data", [])
    if not posts:
        print("   La pagina no tiene publicaciones.")
        return

    p = posts[0]
    print(f"   Publicacion mas reciente: {p['id']}")
    print(f"   {p.get('permalink_url', '(sin link)')}")

    r = requests.get(f"{FBGRAPH}/{p['id']}/comments",
                     params={"fields": "id,message,from", "limit": 50,
                             "access_token": token}, timeout=TIMEOUT)
    ok, d = contar(r)
    if ok:
        print(f"   1. LEER  -> OK, devuelve {len(d.get('data', []))} comentarios")
    else:
        print(f"   1. LEER  -> FALLA: {d}")

    r = requests.post(f"{FBGRAPH}/{p['id']}/comments",
                      data={"message": TEXTO, "access_token": token},
                      timeout=TIMEOUT)
    ok, d = contar(r)
    nuevo = None
    if ok:
        nuevo = d.get("id")
        creados.append(("facebook", nuevo))
        print(f"   2. ESCRIBIR COMENTARIO -> OK, id {nuevo}")
    else:
        print(f"   2. ESCRIBIR COMENTARIO -> FALLA: {d}")

    r = requests.get(f"{FBGRAPH}/{p['id']}/comments",
                     params={"fields": "id,message,from", "limit": 50,
                             "access_token": token}, timeout=TIMEOUT)
    ok, d = contar(r)
    if ok:
        coms = d.get("data", [])
        visto = any(c.get("id") == nuevo for c in coms) if nuevo else False
        print(f"   3. RELEER -> OK, devuelve {len(coms)} comentarios"
              f"{'  (el nuestro aparece)' if visto else ''}")
    else:
        print(f"   3. RELEER -> FALLA: {d}")

    if nuevo:
        r = requests.post(f"{FBGRAPH}/{nuevo}/comments",
                          data={"message": TEXTO_RESPUESTA, "access_token": token},
                          timeout=TIMEOUT)
        ok, d = contar(r)
        if ok:
            hijo = d.get("id")
            creados.append(("facebook", hijo))
            print(f"   4. RESPONDER -> OK, id {hijo}")
        else:
            print(f"   4. RESPONDER -> FALLA: {d}")


def main():
    print("== Diagnostico de comentarios ==")
    print("Esto NO publica historias ni contesta a nadie.")
    print("Escribe un comentario de prueba en la publicacion mas reciente")
    print("y despues intenta leerlo y responderlo.")

    with open(RAIZ / "bot.json", encoding="utf-8") as f:
        cfg = json.load(f)

    cuenta = next((c for c in cfg["cuentas"] if c.get("activa")), None)
    if not cuenta:
        raise SystemExit("No hay ninguna cuenta activa en bot.json.")

    ig = os.environ.get(cuenta["token_secret"], "").strip()
    if ig:
        diagnostico_instagram(cuenta, ig)
    else:
        print(f"   Falta el secret {cuenta['token_secret']}")

    fb_cfg = cuenta.get("pagina_fb")
    fb = os.environ.get(fb_cfg["token_secret"], "").strip() if fb_cfg else ""
    if fb_cfg and fb:
        diagnostico_facebook(fb_cfg, fb)
    else:
        print("   (sin token de Facebook, se saltea esa parte)")

    paso("LO QUE QUEDO PUBLICADO")
    if creados:
        print("   Hay que borrarlo a mano desde la app:")
        for red, ident in creados:
            print(f"     {red}: {ident}")
    else:
        print("   Nada: no se llego a publicar ningun comentario.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
