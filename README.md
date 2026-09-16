# VÉRTICE SPORT — entrega web

**Datos. Contexto. Probabilidad.**

Aplicación web/PWA de análisis de fútbol con BBC + OddsPapi/Betano. El software funciona con datos reales persistidos y mantiene separadas la probabilidad implícita del mercado y la futura probabilidad propia de VÉRTICE.

## Qué funciona ahora

- Escaneo de partidos de fútbol de hoy con BBC.
- Ingesta/persistencia de mercados y cuotas reales de OddsPapi/Betano cuando están disponibles.
- Normalización de mercados y `product_line` sin inventar `fixture_line`.
- **Cuota del Día — MODO MERCADO:** selecciona la oportunidad elegible con mayor probabilidad implícita entre cuotas >= 1.50. No es una predicción propia.
- **Construir Cuota:** busca una combinación cercana a una cuota objetivo usando cuotas reales persistidas; no calcula probabilidad conjunta cuando la correlación es desconocida.
- **Meta de Capital:** calculadora matemática.
- **Ruta hacia la Meta:** simulación de escenarios de riesgo.
- Historial, settlement, readiness, modelo/calibración/walk-forward preparados.
- PWA responsive.
- 184 tests pasando en la entrega base.

## Qué no está activo todavía

El modelo predictivo propio permanece `NOT_READY` hasta disponer de suficiente histórico liquidado y validado. Por tanto:

- `model_probability` = NULL mientras no esté validado.
- EV predictivo = NULL mientras no exista `model_probability`.
- Las selecciones predictivas permanecen en `NO BET TODAY`.
- xG, lesiones, alineaciones, noticias y otras fuentes no disponibles se muestran como MISSING.
- Las cuotas LIVE dependen del acceso real del plan de OddsPapi.

Las calculadoras de capital son simulaciones matemáticas y no garantizan resultados.

## Instalación rápida

### Linux/macOS

```bash
cd vertice-sport
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export VERTICE_TZ=America/New_York
export ODDS_PROVIDER=oddspapi
export ODDS_BOOKMAKERS=betano
export ODDSPAPI_API_KEY='TU_CLAVE_AQUI'
export VERTICE_DB="$(pwd)/data/vertice.db"
cd backend
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### Windows

Puedes ejecutar `START_WINDOWS.bat`. El script pide la API key en la consola y la mantiene solo en la sesión del proceso.

También manualmente:

```bat
cd vertice-sport
py -m pip install -r requirements.txt
set VERTICE_TZ=America/New_York
set ODDS_PROVIDER=oddspapi
set ODDS_BOOKMAKERS=betano
set ODDSPAPI_API_KEY=TU_CLAVE_AQUI
set VERTICE_DB=%CD%\data\vertice.db
cd backend
py -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Abre `http://127.0.0.1:8000`.

## Scan

Pulsa **BUSCAR AHORA**. El POST `/api/scan` hace el scan real. Los módulos de mercado leen después las cuotas ya persistidas en SQLite y no hacen llamadas adicionales por sí mismos.

## Endpoints principales

- `GET /api/scan`
- `POST /api/scan`
- `GET /api/markets`
- `GET /api/daily`
- `GET /api/construir?target=5`
- `GET /api/capital?capital=1&meta=100&cuota=1.5&nivel=MODERADO`
- `GET /api/ruta?capital=1&meta=100&cuota=5`
- `GET /api/readiness`
- `GET /api/history/evaluation`
- `GET /api/model/status`

## PWA

Abre la aplicación en el navegador y usa la opción de instalar aplicación si está disponible. El manifest y service worker están incluidos.

## Backup

```bash
cp data/vertice.db data/vertice.db.bak
```

## Seguridad

Nunca pongas una API key en el frontend, README, Git ni en el ZIP. Usa únicamente `ODDSPAPI_API_KEY` como variable de entorno.

## Pruebas

```bash
python -m pytest -q
```
