#!/usr/bin/env python3
"""
El lector - Dental Ciudad.

Un solo objetivo: encontrar ALGUNA forma de leer los comentarios.

Sabemos que escribir funciona. Leer, por el camino que veniamos usando,
devuelve vacio. Este programa prueba todas las puertas conocidas, una por
una, y dice cual se abre.

Prueba dos llaves distintas:
  - El token de Instagram (app con login de Instagram).
  - El token de la pagina de Facebook (la otra app, otro camino).

Y varias formas de preguntar:
  - La lista de comentarios directa.
  - El contador de comentarios (a veces el numero se ve aunque la lista no).
  - Los comentarios pedidos como campo anidado dentro de la publicacion.
  - Un comentario puntual pedido por su identificador.

No publica ni modifica nada. Solo lee.
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

# El comentario que escribio el diagnostico anterior. Si Eduardo ya lo
# borro, ese intento va a fallar y no pasa nada.
COMENTARIO_CONOCIDO = "18121643648311193"

resultados = []


def probar(nombre, metodo, url, params):
    """Hace la llamada y deja anotado que paso, sin exponer el token."""
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
    except Exception as e:
        print(f"   {nombre}")
        print(f"      ERROR de conexion: {e}")
        resultados.append((nombre, "error"))
        return None

    if not r.ok:
        try:
            e = r.json().get("error", {})
            detalle = f"({e.get('code')}) {e.get('message')}"
        except Exception:
            detalle = r.text[:150]
        print(f"   {nombre}")
        print(f"      RECHAZADO: {detalle}")
        resultados.append((nombre, "rechazado"))
        return None

    d = r.json()
    print(f"   {nombre}")
    print(f"      RESPONDE: {json.dumps(d, ensure_ascii=False)[:400]}")
    resultados.append((nombre, "responde"))
    return d


def titulo(t):
    print()
    print("=" * 72)
    print(t)
    print("=" * 72)


def por_instagram(cuenta, token):
    titulo(f"LLAVE 1: token de Instagram  (@{cuenta['usuario']})")

    d = probar("A. Lista de publicaciones con su contador de comentarios",
               "GET", f"{IGGRAPH}/{cuenta['ig_user_id']}/media",
               {"fields": "id,comments_count,like_count,timestamp",
                "limit": 5, "access_token": token})

    medio = None
    if d and d.get("data"):
        medio = d["data"][0]["id"]

    if not medio:
        print("   (sin publicaciones, no se puede seguir por esta llave)")
        return

    probar("B. Comentarios pedidos como lista suelta",
           "GET", f"{IGGRAPH}/{medio}/comments",
           {"fields": "id,text,username,timestamp", "limit": 50,
            "access_token": token})

    probar("C. Comentarios pedidos como campo anidado de la publicacion",
           "GET", f"{IGGRAPH}/{medio}",
           {"fields": "id,comments_count,comments{id,text,username}",
            "access_token": token})

    probar("D. Un comentario puntual, pedido por su identificador",
           "GET", f"{IGGRAPH}/{COMENTARIO_CONOCIDO}",
           {"fields": "id,text,username,timestamp", "access_token": token})

    probar("E. Respuestas de ese comentario",
           "GET", f"{IGGRAPH}/{COMENTARIO_CONOCIDO}/replies",
           {"fields": "id,text,username", "access_token": token})


def por_pagina(pagina, token):
    titulo(f"LLAVE 2: token de la pagina de Facebook  ({pagina['nombre']})")

    d = probar("F. Que cuenta de Instagram cuelga de esta pagina",
               "GET", f"{FBGRAPH}/{pagina['page_id']}",
               {"fields": "id,name,instagram_business_account",
                "access_token": token})

    ig = None
    if d and d.get("instagram_business_account"):
        ig = d["instagram_business_account"].get("id")
        print(f"      -> cuenta de Instagram vinculada: {ig}")

    if ig:
        d2 = probar("G. Publicaciones de Instagram, vistas desde la pagina",
                    "GET", f"{FBGRAPH}/{ig}/media",
                    {"fields": "id,comments_count,timestamp", "limit": 5,
                     "access_token": token})
        if d2 and d2.get("data"):
            m = d2["data"][0]["id"]
            probar("H. Comentarios de Instagram, con la llave de la pagina",
                   "GET", f"{FBGRAPH}/{m}/comments",
                   {"fields": "id,text,username,timestamp", "limit": 50,
                    "access_token": token})
    else:
        print("   (la pagina no informa cuenta de Instagram vinculada)")

    d3 = probar("I. Publicaciones de la pagina con su contador de comentarios",
                "GET", f"{FBGRAPH}/{pagina['page_id']}/posts",
                {"fields": "id,created_time,comments.summary(true).limit(0)",
                 "limit": 5, "access_token": token})

    if d3 and d3.get("data"):
        p = d3["data"][0]["id"]
        probar("J. Comentarios de esa publicacion, como campo anidado",
               "GET", f"{FBGRAPH}/{p}",
               {"fields": "id,comments{id,message,from}",
                "access_token": token})


def main():
    print("== El lector ==")
    print("Prueba todas las formas conocidas de leer comentarios.")
    print("No publica ni modifica nada.")

    with open(RAIZ / "bot.json", encoding="utf-8") as f:
        cfg = json.load(f)

    cuenta = next((c for c in cfg["cuentas"] if c.get("activa")), None)
    if not cuenta:
        raise SystemExit("No hay ninguna cuenta activa en bot.json.")

    ig = os.environ.get(cuenta["token_secret"], "").strip()
    if ig:
        por_instagram(cuenta, ig)
    else:
        print(f"   Falta el secret {cuenta['token_secret']}")

    fb_cfg = cuenta.get("pagina_fb")
    fb = os.environ.get(fb_cfg["token_secret"], "").strip() if fb_cfg else ""
    if fb_cfg and fb:
        por_pagina(fb_cfg, fb)
    else:
        print("   (sin token de Facebook, se saltea esa llave)")

    titulo("RESUMEN")
    for nombre, estado in resultados:
        marca = {"responde": "RESPONDE ", "rechazado": "RECHAZADO",
                 "error": "ERROR    "}[estado]
        print(f"   {marca}  {nombre}")
    print()
    print("Lo que importa no es que diga RESPONDE, sino si adentro de la")
    print("respuesta viene texto de comentarios o viene vacio.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
