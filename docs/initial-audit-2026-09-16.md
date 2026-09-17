# VÉRTICE SPORT — Auditoría inicial

Fecha: 2026-09-16
Rama: `improvements/initial-audit`

## Hallazgos confirmados en la revisión estática

- El modelo permanece explícitamente en `NOT_READY` y no se fuerza una probabilidad propia.
- El modo de mercado etiqueta la probabilidad como `MARKET` y utiliza la probabilidad implícita de la cuota.
- La ruta de escaneo registra estados de ejecución y errores de persistencia en `scan_runs`.
- El acceso público de Betano está marcado como restringido; no debe presentarse como una fuente disponible en tiempo real.
- Las respuestas de análisis e historial mantienen `model_probability` y `EV` en `null` mientras el modelo no esté listo.

## Pendientes antes de modificar lógica crítica

- Ejecutar la suite de pruebas en un entorno con las dependencias del proyecto.
- Revisar los módulos de ingestión y normalización de cuotas junto con sus pruebas.
- Validar el comportamiento de `/api/scan` cuando BBC no devuelve partidos o falla la persistencia.
- Revisar la configuración CORS para despliegues públicos.
- No activar recomendaciones predictivas hasta cumplir los criterios de readiness y validación histórica.

Este documento no declara que la aplicación esté completamente validada: registra el estado de la revisión estática y los pasos que requieren ejecución de pruebas.
