# VÉRTICE SPORT — ejecución

## Backend
```bash
cd vertice-sport
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export VERTICE_TZ=America/New_York
export ODDS_PROVIDER=oddspapi
export ODDS_BOOKMAKERS=betano
export ODDSPAPI_API_KEY=   # solo en el entorno, nunca en git
export VERTICE_DB="$(pwd)/data/vertice.db"
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000
```

Frontend: el mismo proceso sirve `GET /` (`frontend/index.html`).

## Scan
`POST /api/scan` o botón **BUSCAR AHORA**.

## PWA
Abrir `http://localhost:8000`, instalar desde el navegador (manifest + sw.js).

## Backup
`cp data/vertice.db data/vertice.db.bak`

## Secretos
Nunca en frontend, README o Git. Solo `ODDSPAPI_API_KEY`.
