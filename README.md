# JobHunter AI

MVP de un sistema transparente para buscar vacantes, comparar requisitos contra un perfil profesional y generar una versión ATS-friendly del CV sin inventar información.

## Qué hace este MVP

1. Carga un perfil estructurado basado en el CV original.
2. Lee vacantes en JSON.
3. Calcula compatibilidad con una fórmula explicable:
   - 60% requisitos obligatorios.
   - 25% requisitos deseables.
   - 15% palabras clave.
4. Separa requisitos cumplidos y faltantes.
5. Adjunta evidencia del CV para cada coincidencia.
6. Descarta vacantes bajo el umbral configurado.
7. Genera `alerts.json` y un `cv_adaptado_<id>.md` por vacante compatible.
8. Descarta antes del matching las vacantes que no correspondan a prácticas, medio tiempo, trainee, apprenticeship o posiciones estudiantiles.

El MVP usa datos de ejemplo para que sea reproducible. La siguiente etapa añadirá adaptadores de fuentes reales, deduplicación, alertas y revisión humana antes de postular.

## Privacidad y GitHub

`data/profile.json`, el PDF original y los archivos generados en `output/` son
locales y están excluidos de Git para no publicar teléfono, correo ni el CV
personal. Usa `data/profile.example.json` como plantilla pública y crea tu
propio `data/profile.json` local.

## Arquitectura

```text
Fuentes de vacantes -> Normalizador -> Matcher explicable -> Filtro
                                            |
                                            +-> Evidencia y análisis
                                            +-> CV ATS adaptado -> Alertas
```

La separación principal está en `models.py`, `matcher.py`, `tailor.py` y `pipeline.py`. En una versión posterior, los conectores web solo tendrán que producir el mismo modelo `Job`.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -e .
```

## Uso

Extraer texto del PDF original:

```bash
python -m jobhunter_ai.cli parse-cv upload/CV_Gilberto_MoralesM.pdf
```

Después de revisar la extracción, el perfil estructurado se guarda localmente
en `data/profile.json`. Ese archivo no debe subirse a un repositorio público.

Ejecutar el análisis de demostración:

```bash
python -m jobhunter_ai.cli run \\
  --profile data/profile.json \\
  --jobs data/sample_jobs.json \\
  --preferences data/preferences.json \\
  --output output \\
  --threshold 60
```

Archivos generados:

- `output/alerts.json`: vacante, porcentaje, requisitos cumplidos/faltantes, evidencia y ruta del CV.
- `output/cv_adaptado_<id>.md`: CV adaptado y legible por ATS.
- `data/preferences.json`: tipos de empleo permitidos y palabras excluidas.

Para aceptar otra modalidad, edita `allowed_employment_types`. Los valores
soportados por el MVP son `internship`, `part-time`, `trainee`,
`apprenticeship` y `student`. Si una vacante no declara modalidad, se descarta
por seguridad mientras `allow_unknown_employment_type` sea `false`.

Pruebas:

```bash
python -m unittest discover -s tests -v
```

## Jobicy

JobHunter puede consultar la API pública de Jobicy mediante la configuración
de `data/sources.example.json` y conservar el enlace original de cada vacante.
La API no requiere API key. El sistema debe consultar Jobicy como máximo una
vez por hora; este adaptador no implementa programación periódica ni caché.

## Alertas locales por correo

JobHunter puede convertir mensajes RFC 822 (`.eml`) exportados localmente en
vacantes, sin conectarse a Gmail ni usar credenciales. Los correos reales deben
guardarse únicamente en `data/email_alerts/`; esta carpeta es privada, está
excluida de Git y nunca debe subirse al repositorio.

```bash
python -m jobhunter_ai.cli run \
  --profile data/profile.json \
  --email-alerts data/email_alerts/ \
  --preferences data/preferences.json \
  --output output
```

También puede declararse dentro de una configuración `--sources` con
`{"type": "email", "path": "ruta/a/alertas", "provider": "opcional"}`.
La ruta puede ser una carpeta o un único archivo `.eml`. Si no se configura
`provider`, se utiliza el dominio del remitente.

## Gmail por etiqueta (solo lectura)

`GmailLabelJobSource` puede leer únicamente los mensajes de una etiqueta de
Gmail resuelta por nombre. Por defecto usa `JobHunter/Alertas`, solicita
exclusivamente el scope `https://www.googleapis.com/auth/gmail.readonly` y no
envía, elimina, archiva, marca como leído ni modifica mensajes.

```bash
python -m jobhunter_ai.cli run \
  --profile data/profile.json \
  --gmail-token data/gmail_token.json \
  --gmail-label JobHunter/Alertas \
  --gmail-allowed-domain occ.example \
  --gmail-allowed-domain indeed.example,linkedin.example \
  --gmail-max-messages 50 \
  --preferences data/preferences.json \
  --output output
```

También puede usarse `data/sources.gmail.example.json` con `--sources`. Los
dominios del ejemplo son sintéticos y deben reemplazarse localmente por los
proveedores autorizados. El conector descarta cualquier otro dominio y no
guarda el mensaje raw ni su HTML en archivos o logs.

El siguiente paso será realizar una autorización OAuth única con una aplicación
de escritorio configurada en Google Cloud. Esta entrega no implementa ese flujo:
solo lee un token local ya autorizado. `data/gmail_token.json` está excluido de
Git y nunca debe subirse al repositorio, copiarse a artifacts ni imprimirse.

## Historial y deduplicación local

La opción `--state-db` activa un historial SQLite local para evitar que una
vacante cuya alerta ya fue confirmada vuelva a generar una alerta o un CV
adaptado:

```bash
python -m jobhunter_ai.cli run \
  --profile data/profile.json \
  --sources data/sources.example.json \
  --state-db data/jobhunter.db \
  --output output
```

La base conserva únicamente hashes SHA-256 del identificador y del enlace,
la fuente, fechas, estado y score. No almacena el texto de la vacante o del
correo, el perfil ni el CV. Un cambio de fuente, identificador o enlace se
considera una vacante nueva; los parámetros habituales de seguimiento del
enlace no alteran su identidad. `data/jobhunter.db` está excluido de Git.

SQLite es persistencia exclusivamente local. El pipeline deja las coincidencias
en estado `compatible`; un canal de alertas debe confirmar el envío mediante la
operación explícita del almacenamiento antes de cambiarlo a `alertado`. Mientras
esa confirmación no exista, la vacante puede volver a procesarse. Esta base aún
no se conserva entre ejecuciones independientes de GitHub Actions.

## Ejecución remota con GitHub Actions

El workflow `Remote Job Search` puede ejecutarse manualmente o cada seis horas.
Usa Jobicy mediante `data/sources.example.json`, genera los resultados de forma
temporal y envía por Telegram las vacantes compatibles junto con su CV adaptado.
`profile.json`, el PDF y `output/` no se publican como artifacts y se eliminan al
terminar la ejecución.

Configura estos tres secretos obligatorios del repositorio en **Settings > Secrets and
variables > Actions**:

- `PROFILE_JSON`: contenido completo del perfil local `data/profile.json`.
- `TELEGRAM_BOT_TOKEN`: token del bot de Telegram.
- `TELEGRAM_CHAT_ID`: identificador del chat que recibirá las alertas.

Opcionalmente, configura `SEARCH_PREFERENCES_JSON` con el contenido de tus
preferencias avanzadas. Durante la ejecución se guarda temporalmente con
permisos restrictivos y se elimina siempre al finalizar. Si el secreto no está
configurado, el workflow conserva `data/preferences.json` como configuración.

No guardes los valores en el repositorio ni los incluyas en archivos de workflow.

## Reglas de integridad

- No se agregan habilidades, experiencia, estudios o certificaciones que no estén en el perfil derivado del CV.
- La adaptación cambia orden, selección y énfasis; no cambia los hechos.
- Cada coincidencia relevante conserva una referencia a sección y texto fuente.
- Una persona debe revisar el resultado final antes de enviarlo a una vacante.

## Evolución propuesta

- `sources/`: adaptadores para APIs, RSS o exportaciones permitidas por cada bolsa de trabajo.
- `storage/`: SQLite para historial, deduplicación y estado de postulaciones.
- `alerts/`: correo, Telegram o una interfaz web.
- `llm/`: extracción y redacción asistida con validación contra claims/evidencias.
- `scheduler/`: ejecución periódica con límites, logs y reintentos.
- `web/`: dashboard para revisar, editar y aprobar CVs antes de postular.
