# NORA Core API v0.1

Primera API independiente para NORA Smart Watch.

## Objetivo

Validar el flujo:

NORA Watch -> HTTPS -> NORA Core -> OpenAI -> respuesta breve -> Watch/TTS

No modifica ni reemplaza NORA Desktop.

## Requisitos

- Python 3.11 recomendado
- Variable de entorno `OPENAI_API_KEY`

## Ejecución local

Crear entorno virtual e instalar:

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

En Windows:

    .venv\Scripts\activate

Ejecutar:

    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Abrir:

    http://127.0.0.1:8000/docs

## Endpoints

- GET `/`
- GET `/health`
- POST `/api/watch/ask`

Ejemplo:

    {
      "question": "Dame una definición sencilla de polimorfismo.",
      "client": "WATCH"
    }

Respuesta esperada:

    {
      "success": true,
      "answer": "...",
      "speak": true
    }

## cPanel / Passenger

`passenger_wsgi.py` ya viene incluido.

FastAPI es ASGI. Para esta primera versión se utiliza `a2wsgi.ASGIMiddleware`
para adaptar la aplicación a un servidor Passenger/WSGI.

En cPanel, la raíz de la aplicación debe apuntar a la carpeta que contiene
`passenger_wsgi.py`.

Instalar `requirements.txt` dentro del entorno virtual asignado por cPanel y
configurar `OPENAI_API_KEY` como variable de entorno de la aplicación.

Después reiniciar la aplicación desde cPanel.

Primero comprobar `/health` y luego `/docs`.

## Seguridad v0.1

Esta versión está destinada a validar conectividad y arquitectura.
Antes de exponerla como API de producción para el reloj se agregará
autenticación del cliente Watch, límites de solicitudes y controles
adicionales.
