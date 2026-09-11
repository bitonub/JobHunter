# JobHunter AI

> **v0.1.0 — MVP funcional y reproducible**

Sistema en Python para filtrar vacantes, compararlas de forma explicable con un perfil profesional y preparar un CV en Markdown compatible con ATS. El proyecto prioriza la trazabilidad: no inventa habilidades, experiencia, estudios ni certificaciones.

## Problema que resuelve

Buscar empleo suele requerir revisar muchas vacantes que no coinciden con la disponibilidad, el nivel o el perfil de una persona. JobHunter AI automatiza la parte de **análisis y priorización**, pero mantiene la decisión y la postulación bajo control humano.

No envía postulaciones automáticamente.

## Capacidades incluidas

- Carga un perfil estructurado derivado del CV original.
- Lee vacantes de archivos JSON y adaptadores normalizados.
- Filtra antes del matching puestos fuera de prácticas, medio tiempo, trainee, apprenticeship o student.
- Excluye por configuración términos de nivel como `senior`, `lead`, `manager` y `director`.
- Calcula un porcentaje de compatibilidad explicable:
  - 60% requisitos obligatorios.
  - 25% requisitos deseables.
  - 15% palabras clave.
- Informa requisitos cumplidos, faltantes y evidencia del perfil para cada coincidencia.
- Genera `alerts.json` y, únicamente para vacantes compatibles, un `cv_adaptado_<id>.md`.
- Mantiene deduplicación e historial local con SQLite.
- Puede leer localmente alertas RFC 822 (`.eml`) o mensajes de una etiqueta de Gmail en modo solo lectura.
- Incluye una cola de revisión para vacantes técnicas que no declaran tipo de empleo, sin enviarlas al matching ni generar un CV.
- Incluye pruebas automatizadas y un workflow de integración continua.

## Arquitectura

```text
Fuentes normalizadas
        |
        v
Validación de calidad -> Filtros de preferencias -> Matcher explicable
                                                        |
                                                        +-> Evidencia y análisis
                                                        +-> CV ATS adaptado
                                                        +-> Reporte / revisión humana
```

La separación principal del código está en `models.py`, `sources/`, `matcher.py`, `tailor.py`, `pipeline.py` y `storage.py`. Un nuevo conector solo necesita producir el modelo común `Job`.

## Uso local

Requisitos: Python 3.10 o superior.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Crea tu perfil privado a partir de la plantilla pública:

```powershell
Copy-Item data\profile.example.json data\profile.json
```

Ejecuta la demostración con vacantes de ejemplo:

```powershell
python -m jobhunter_ai.cli run --profile data/profile.json --jobs data/sample_jobs.json --preferences data/preferences.json --output output --threshold 60
```

Para extraer texto de un CV PDF local:

```powershell
python -m jobhunter_ai.cli parse-cv ruta\a\mi_cv.pdf
```

Ejecuta las pruebas:

```powershell
python -m unittest discover -s tests -v
```

## Resultados

- `output/alerts.json`: vacante, puntuación, requisitos cumplidos/faltantes, evidencia y ruta del CV generado.
- `output/cv_adaptado_<id>.md`: adaptación ATS que reorganiza y enfatiza información existente.
- `output/review_queue.md`: vacantes que requieren verificar manualmente modalidad o tipo de empleo.

## Privacidad y límites

Nunca subas a GitHub:

- `data/profile.json`
- CVs PDF originales
- `data/google_client_secret.json` y `data/gmail_token.json`
- `data/jobhunter.db`
- `data/email_alerts/`
- `data/search_preferences.json`
- contenido de `output/`
- tokens, API keys o secretos de GitHub Actions

El repositorio incluye solo plantillas y datos de demostración. Antes de postularse, una persona debe revisar tanto la vacante como el CV generado.

## Integraciones disponibles

- **JSON, RSS/Atom y Jobicy:** adaptadores para datos normalizados y demostraciones.
- **Correo local:** procesamiento de archivos `.eml` privados.
- **Gmail por etiqueta:** lectura local con OAuth y scope `gmail.readonly`; el código limita la consulta a la etiqueta configurada y no modifica mensajes.
- **Telegram/GitHub Actions:** existe un workflow remoto experimental para resultados temporales basados en Jobicy.

Estas integraciones no significan que el sistema tenga una búsqueda universal de todas las bolsas de empleo. La calidad final depende de que el proveedor incluya título, empresa, descripción, enlace real y tipo de empleo verificable.

## Decisiones de integridad

- No agrega hechos que no aparezcan en el perfil derivado del CV.
- Cada coincidencia conserva evidencia de la sección y texto fuente.
- Una vacante sin tipo de empleo verificable no se acepta automáticamente.
- Los enlaces de demostración o sintéticos se rechazan.
- La postulación final siempre requiere aprobación humana.

## Roadmap posterior a v0.1.0

- Conectores permitidos y fiables para fuentes reales de empleo.
- Persistencia compartida para ejecuciones remotas.
- Scheduler con límites, registros y reintentos.
- Dashboard de revisión, edición y aprobación.
- Alertas con fuentes de datos verificadas.
- Apoyo de LLM validado estrictamente contra la evidencia del perfil.
- Contenedores y despliegue de producción.

## Para portafolio

**JobHunter AI** demuestra diseño de pipelines en Python, modelos de datos, filtros configurables, matching explicable, generación responsable de documentos, privacidad de datos y pruebas automatizadas.

