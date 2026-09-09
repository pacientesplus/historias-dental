# Automatización de redes — Dental Ciudad

Este repositorio es **el depósito**. Todo lo que hace funcionar las redes de
Dental Ciudad de forma automática vive acá: los programas, la configuración y
este documento. Si entrás y no te acordás de nada, empezá leyendo esto.

**Cliente:** Dental Ciudad (dos sedes: Microcentro y Once)
**Cuentas que maneja:** 3 de Instagram y 3 páginas de Facebook
**A cargo:** Eduardo

---

## Las tres cuentas

| Instagram | Página de Facebook | Sede que le asignamos |
|---|---|---|
| @dentalciudad1 | Dental Ciudad 1 | Microcentro |
| @dentalciudad | Dental Ciudad | Once |
| @dentalmicrocentro | Dental Microcentro | Microcentro |

Los dos WhatsApp:

- **Microcentro:** https://wa.me/5491124577716
- **Once:** https://wa.me/5491161460061

---

## Qué hay armado

### 1. Publicador de historias — ANDANDO

Todos los días a las **8:00 de la mañana** (hora de Argentina) publica una
historia en las tres cuentas de Instagram y en las tres páginas de Facebook.

Cómo funciona, en criollo:

1. Mira la carpeta de Google Drive **"Automatic histories"**, donde Eduardo
   tira fotos y videos desde el celular.
2. Elige **una** pieza al azar, con memoria: prioriza las que hace más tiempo
   que no salen, y las que salieron hace menos de 21 días no vuelven a salir.
   Si el mismo archivo está subido dos veces, cuenta como uno solo.
3. La acomoda: vertical 1080x1920, videos hasta 60 segundos, fotos a JPG
   (entiende HEIC del iPhone y MOV).
4. La sube a un lugar público temporal para que Instagram y Facebook la puedan
   descargar.
5. La publica como historia en las seis cuentas.
6. Anota lo que publicó para no repetir.

Si una cuenta falla, las otras salen igual. Si Facebook falla, Instagram sale
igual, y al revés.

### 2. Bot de comentarios — EN MODO PRUEBA

Lee los comentarios de las publicaciones, decide cuáles merecen respuesta, la
redacta con inteligencia artificial siguiendo un guion, contesta abajo del
comentario y le manda un privado a esa misma persona.

**Hoy está en modo prueba: no publica ni manda nada.** Escribe en el registro
lo que *habría* contestado, para poder leerlo antes de soltarlo.

Reglas que tiene metidas a fuego:

- No da precios. Nunca. Deriva al WhatsApp.
- No diagnostica ni opina sobre el caso de la persona.
- No promete resultados ni tiempos.
- No responde quejas, reclamos ni insultos: los marca para que los vea una
  persona.
- No responde emojis sueltos ni arrobas a amigos.
- Las tres cuentas no se responden entre ellas.
- No responde dos veces el mismo comentario.
- Nunca dice que es un bot.

**Detalle importante de los links:** en los comentarios de Instagram los links
no se pueden tocar, son texto muerto. Por eso ahí no pone ninguno y deriva al
privado. En el privado de Instagram y en todo Facebook sí manda el link de la
sede que corresponde.

---

## Los archivos, uno por uno

### Los que podés tocar vos

| Archivo | Para qué sirve |
|---|---|
| `instrucciones.txt` | **El guion del bot.** Todo lo que dice y lo que no. Es texto común: lo abrís, apretás el lapicito, escribís, guardás. Acá venís cuando querés cambiarle el discurso. |
| `config.json` | Ajustes del publicador de historias: cuántas por día, días de descanso, qué cuentas están activas. |
| `bot.json` | Ajustes del bot de comentarios: modo prueba encendido o apagado, cuántas horas para atrás mira, la lista de palabras que lo hacen callarse. |

### Los que no conviene tocar

| Archivo | Qué es |
|---|---|
| `publicar.py` | El programa de las historias. |
| `responder.py` | El programa del bot de comentarios. |
| `.github/workflows/publicar.yml` | El reloj de las historias (8:00 de la mañana). |
| `.github/workflows/responder.yml` | La tarea del bot, por ahora solo manual. |
| `historial.json` | Memoria del publicador: qué pieza salió y cuándo. Se escribe solo. |
| `respondidos.json` | Memoria del bot: qué comentarios ya contestó y cuáles quedaron marcados para revisar. Se escribe solo. |

---

## Las llaves (Secrets)

Ninguna clave está escrita en los archivos. Todas viven en
**Settings → Secrets and variables → Actions**.

| Secret | Para qué | ¿Vence? |
|---|---|---|
| `IG_TOKEN_DENTALCIUDAD1` | Instagram de esa cuenta | **Sí, cada 60 días** |
| `IG_TOKEN_DENTALCIUDAD` | Instagram de esa cuenta | **Sí, cada 60 días** |
| `IG_TOKEN_DENTALMICROCENTRO` | Instagram de esa cuenta | **Sí, cada 60 días** |
| `FB_TOKEN_DENTALCIUDAD1` | Página de Facebook | No vence |
| `FB_TOKEN_DENTALCIUDAD` | Página de Facebook | No vence |
| `FB_TOKEN_DENTALMICROCENTRO` | Página de Facebook | No vence |
| `GOOGLE_API_KEY` | Leer la carpeta de Drive | No vence |
| `GEMINI_API_KEY` | La inteligencia artificial que redacta | No vence |

**Para reemplazar una llave:** no uses "New repository secret" (te va a decir
que ya existe). Andá al secret que querés cambiar y apretá el **lapicito**.
Link directo:

    github.com/pacientesplus/historias-dental/settings/secrets/actions/NOMBRE_DEL_SECRET

### De dónde sale cada llave

- **Los tres de Instagram:** app de Meta "Dental Ciudad 1 - Historias"
  (ID 3590109467851346) → Instagram API → *API setup with Instagram login* →
  *Generate access tokens* → botón "Generate token" al lado de cada cuenta.
- **Los tres de Facebook:** Explorador de la API Graph → generás un token de
  usuario → lo ampliás en el Depurador de Tokens ("Extend Access Token") →
  con ese token largo consultás `me/accounts?fields=name,access_token` y te
  devuelve los tres tokens de página juntos.
- **Google:** consola de Google Cloud, clave de API con acceso a Drive.
- **Gemini:** aistudio.google.com/apikey, nivel gratuito.

---

## Cómo hacer las cosas

**Publicar una historia ahora, sin esperar a las 8:00**
Actions → "Publicar historias" → Run workflow → Run workflow.
Ojo: publica de verdad, en las seis cuentas.

**Probar el bot de comentarios**
Actions → "Responder comentarios" → Run workflow → Run workflow.
Mientras `bot.json` diga `"modo_prueba": true`, no publica nada: solo muestra.

**Ver qué pasó en una corrida**
Actions → la corrida → clic en el paso "Publicar" o "Responder". Ahí está todo
lo que hizo, línea por línea.

**Apagar todo de golpe**
Actions → el workflow → los tres puntitos arriba a la derecha → *Disable
workflow*. Se apaga hasta que lo vuelvas a habilitar. Nada se pierde.

**Apagar una sola cuenta**
En `config.json` (historias) o `bot.json` (comentarios), poné
`"activa": false` en esa cuenta.

**Cambiar el horario de las historias**
En `.github/workflows/publicar.yml`, la línea del `cron`. Está en horario
UTC: Argentina es UTC menos 3, así que `0 11` = 8:00 de la mañana acá.

**Cambiarle el discurso al bot**
Editá `instrucciones.txt` y listo. No hace falta tocar nada más.

---

## Cosas a tener en cuenta

**El repositorio es público.** Tiene que serlo para que Instagram y Facebook
puedan descargar los archivos que publica. Por eso ninguna clave va escrita en
los archivos, y por eso no hay que subir acá nada del cliente que no pueda ver
cualquiera.

**Los tokens de Instagram vencen cada 60 días.** Cuando venzan, las historias
dejan de salir y el registro de la corrida lo va a decir. Se regeneran en el
panel de Meta, en la pantalla de *Generate access tokens*.

**Al generar un token nuevo, el viejo deja de servir.** Si generás y no lo
pegás en GitHub, esa cuenta se rompe hasta que lo pegues. Nunca dejes el
trámite por la mitad.

**Un token es una sola llave para varias puertas.** El mismo token de
Instagram sirve para publicar historias y para responder comentarios. Si lo
cambiás por uno con menos permisos, se rompen las dos cosas.

**Los comentarios de los anuncios no están cubiertos todavía.** El bot mira
las publicaciones del perfil. Los comentarios de la pauta (los "dark posts")
viven en otro lado y necesitan permisos de publicidad. Es una segunda etapa.

**El mensaje privado a desconocidos puede requerir revisión de Meta.** Está
programado y listo, pero hasta que no se pruebe con una persona real no se
sabe si el nivel de acceso actual alcanza o hay que pasar por el trámite de
App Review.

**El copy de la clínica dice que no usan bots.** Es una decisión de Eduardo,
tomada a conciencia: el bot no conversa ni se hace pasar por odontólogo,
orienta por encima y deriva a una persona real, que es la asistente del
WhatsApp. Vale la pena tenerlo presente si alguna vez alguien lo señala.

**Gemini tiene un límite gratuito diario.** Si algún día el volumen de
comentarios lo supera, el bot va a fallar en las redacciones y el registro lo
va a decir. Ahí habría que pasar a un plan pago, que igual es de centavos.

---

## Qué falta

- [ ] Rehacer los tres tokens de Facebook agregando `pages_manage_engagement`
      y `pages_read_user_content` (sin eso no puede leer comentarios en FB)
- [ ] Correr el bot en modo prueba y revisar juntos las respuestas
- [ ] Probar el mensaje privado con Eduardo como destinatario, no con un
      paciente real
- [ ] Sacarle el modo prueba y ponerle un horario automático
- [ ] Segunda etapa: comentarios de los anuncios
