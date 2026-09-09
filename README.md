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
