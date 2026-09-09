# Dónde quedamos — 9 de septiembre de 2026

Este archivo es la bitácora: dónde se dejó el trabajo y qué sigue.
El manual general está en el README.

---

## Historias — TERMINADO Y ANDANDO

Publica una historia por día a las 8:00 de la mañana en las tres cuentas de
Instagram y en las tres páginas de Facebook. Probado el 8 de septiembre: salió
en las seis. No hay nada pendiente acá.

---

## Bot de comentarios — PROGRAMADO, TRABADO EN UN PUNTO

Todo el código está escrito, subido y probado con casos falsos: filtra los
comentarios que no merecen respuesta, ignora quejas y las marca aparte, no se
contesta entre las tres cuentas, no repite, y sabe que en los comentarios de
Instagram los links no funcionan (ahí deriva al privado) mientras que en
Facebook sí los pone.

**Lo que no funciona todavía: no consigue ver los comentarios reales.**

### Lo que se comprobó

Corriendo la prueba cuatro veces, en modo prueba (sin publicar nada):

- Instagram responde bien: encuentra las 12 publicaciones de cada cuenta, sin
  ningún error.
- Al pedir los comentarios de esas 36 publicaciones, contesta que están
  **vacías en todas**. No dice "falta permiso": dice que no hay.
- Se descartó que fuera la ventana de tiempo. Se probó con 24 horas, con 30
  días y con 3 años. Siempre cero.
- Se descartó que fuera el permiso: `instagram_business_manage_comments` se
  agregó a la app y los tres tokens se regeneraron **después** de agregarlo.
- Eduardo confirmó mirando el celular que casi todas las publicaciones tienen
  comentarios.

### La hipótesis que queda

La app está en **modo desarrollo**. En ese modo Meta devuelve los datos propios
completos pero esconde los de terceros. Los comentarios son de otras personas.
Encaja con todo lo observado: ve sus publicaciones, no ve quién comentó.

### La prueba que lo define

Eduardo deja un comentario **desde su cuenta personal de Instagram** en la
última publicación de @dentalciudad1. Después se corre el bot otra vez
(Actions → "Responder comentarios" → Run workflow).

- Si el bot lo ve → el bloqueo es otro y hay que seguir buscando.
- Si el bot no lo ve → confirmado. Hay que pasar la app a **modo Live** y hacer
  la revisión de Meta (App Review).

Esa misma revisión habilita también los **mensajes privados a desconocidos**,
que hoy están programados pero sin confirmar. O sea que se resuelven los dos
problemas con un solo trámite.

---

## Facebook — PENDIENTE, INDEPENDIENTE DE LO ANTERIOR

Al leer comentarios, las tres páginas devuelven:

    (#200) Missing Permissions

Los tokens de página sirven para publicar pero no para leer ni responder
comentarios. Hay que rehacerlos agregando dos permisos:

- `pages_manage_engagement`
- `pages_read_user_content`

Se sacan igual que la vez pasada: Explorador de la API Graph → token de usuario
con esos permisos → ampliarlo en el Depurador de Tokens → consultar
`me/accounts?fields=name,access_token` → los tres tokens de página salen
juntos → pegarlos en sus secrets.

Esto no depende de la incógnita de Instagram: se puede hacer cuando se quiera.

---

## Lo que sigue, en orden

1. La prueba del comentario propio (dos minutos, define todo lo demás).
2. Según el resultado: la revisión de Meta, o buscar otra causa.
3. Rehacer los tres tokens de Facebook con los dos permisos que faltan.
4. Leer juntos las respuestas que el bot escribiría, todavía en modo prueba.
5. Probar el mensaje privado con Eduardo como destinatario, no con un paciente.
6. Sacarle el modo prueba y ponerle horario automático.
7. Segunda etapa: los comentarios de los anuncios.

---

## Cosas que costaron y conviene no volver a tropezar

- **Para reemplazar un secret no se usa "New repository secret"**: rebota
  diciendo que ya existe. Hay que entrar al secret y apretar el lapicito.
- **Al generar un token nuevo, el viejo deja de servir.** Generar, copiar y
  pegar en GitHub de una, sin dejar el trámite por la mitad.
- **No guardar tokens en documentos aparte.** GitHub Secrets es la caja fuerte;
  si se pierde uno, se genera otro y listo.
- **Los tokens de Instagram vencen cada 60 días.** Los de página de Facebook no
  vencen.
