"""
Punto de Entrada Unificado de VarSQL (Estudio Relacional Auditado y Sala de Revisión SQL).
Se ejecuta de forma nativa en Windows como una aplicación de escritorio independiente (mediante pywebview / WebView2),
arrancando el motor FastAPI + SQLite en segundo plano en un puerto local libre y cerrándolo limpiamente al cerrar la ventana.
"""

from __future__ import annotations
import argparse
from contextlib import asynccontextmanager
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

# En ejecutable Windows (--windowed), sys.stdout y sys.stderr pueden ser None; evitar crash en logging de uvicorn
import os
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# Garantizar que el entorno virtual local (.venv) esté en sys.path cuando se ejecuta desde código fuente
IS_FROZEN = getattr(sys, "frozen", False)
if IS_FROZEN:
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parent
    BUNDLE_DIR = ROOT_DIR
    VENV_SITE_PACKAGES = ROOT_DIR / ".venv" / "Lib" / "site-packages"
    if VENV_SITE_PACKAGES.exists() and str(VENV_SITE_PACKAGES) not in sys.path:
        sys.path.insert(0, str(VENV_SITE_PACKAGES))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from backend import APP_VERSION
from backend.api.routes import WORKSPACES_DIR, engine, router as api_router

FRONTEND_DIR = BUNDLE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="VarSQL · Estudio Relacional Auditado y Sala de Revisión SQL",
        description="Sistema de Gestión de Bases de Datos Relacional Determinista, Auditado y Didáctico",
        version=APP_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    app.include_router(api_router)

    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)

    @app.get("/", include_in_schema=False)
    def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app


app = create_app()


def find_available_port(host: str, preferred_port: int) -> int:
    """Devuelve el puerto preferido si está libre, o busca el siguiente puerto local disponible."""
    for port in range(preferred_port, preferred_port + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return preferred_port


def wait_for_server(url: str, timeout_s: float = 8.0) -> bool:
    deadline = time.time() + timeout_s
    health_url = f"{url}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=0.6) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Aplicación de Escritorio VarSQL")
    parser.add_argument("--host", default="127.0.0.1", help="Host local (por defecto 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Puerto local preferido (por defecto 8000)")
    parser.add_argument(
        "--web",
        action="store_true",
        help="Ejecutar en modo servidor web tradicional sin ventana nativa de escritorio",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="En modo --web, no abrir automáticamente el navegador",
    )
    args = parser.parse_args()

    port = find_available_port(args.host, args.port)
    url = f"http://{args.host}:{port}"

    # Modo servidor web tradicional (solo si se solicita explícitamente con --web)
    if args.web:
        print("=" * 76)
        print("  VarSQL · Modo Servidor Local")
        print(f"  Servidor Local Activo en: {url}")
        print(f"  Directorio de Proyectos : {WORKSPACES_DIR}")
        print("=" * 76)
        if not args.no_browser:
            threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        uvicorn.run(app, host=args.host, port=port, log_config=None if IS_FROZEN else uvicorn.config.LOGGING_CONFIG)
        return

    # Modo Aplicación Nativa de Escritorio Windows (por defecto, sin abrir Chrome)
    import webview
    from backend.api import routes as api_routes

    config = uvicorn.Config(app, host=args.host, port=port, log_config=None)
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    if not wait_for_server(url, timeout_s=10.0):
        server.should_exit = True
        server_thread.join(timeout=2.0)
        raise RuntimeError(
            f"No se pudo iniciar el servidor local de VarSQL en {url} dentro del tiempo límite."
        )

    window = webview.create_window(
        title="VarSQL · Estudio Relacional y Auditoría SQL",
        url=url,
        width=1420,
        height=880,
        min_size=(640, 520),
        background_color="#0b0d12",
        resizable=True,
        maximized=True,
    )
    api_routes.NATIVE_WINDOW = window

    try:
        webview.start(debug=False)
    except Exception as exc:
        print(f"[VarSQL] Ventana nativa no disponible ({exc}). Abriendo en navegador en {url}...")
        webbrowser.open(url)
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass
    finally:
        server.should_exit = True
        server_thread.join(timeout=2.0)


if __name__ == "__main__":
    main()
