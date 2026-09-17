# Plan de endurecimiento de `/api/scan`

## Objetivo

Validar el flujo de escaneo sin activar recomendaciones predictivas ni ocultar errores de proveedores o persistencia.

## Casos que deben cubrirse

1. Respuesta válida del proveedor de partidos.
2. Respuesta vacía sin tratarla como error de proveedor.
3. Error de parseo del proveedor con estado `FAILED`.
4. Error de persistencia con `persist_ok=false` y advertencia explícita.
5. Fallo al crear o actualizar el registro de `scan_runs` sin afirmar que el escaneo se completó correctamente.
6. Conservación de `recommendation: NO BET TODAY` mientras las capas de cuotas y modelo no estén listas.

## Criterios de aceptación

- Los estados de `scan_runs` reflejan el avance real del proceso.
- Los errores se devuelven de forma estructurada y se registran.
- No se generan probabilidades propias, EV ni recomendaciones predictivas cuando `model_status` es `NOT_READY`.
- Cada caso crítico queda cubierto por una prueba automatizada.
