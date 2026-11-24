# Contribuir a VarSQL

Gracias por tu interés en contribuir a **VarSQL**.

## Flujo recomendado

1. Haz un **fork** del repositorio y crea una rama descriptiva:
   ```bash
   git checkout -b feat/mi-mejora
   ```
2. Instala las dependencias en un entorno virtual:
   ```bash
   python -m venv .venv
   pip install -r requirements.txt
   ```
3. Mantén el principio rector del proyecto: **100 % determinista, offline y con validación de seguridad antes de tocar el disco**.
4. Añade o actualiza pruebas en `tests/test_varsql.py` para cualquier cambio en el motor (`backend/core/`) o en la API (`backend/api/`).
5. Ejecuta la suite completa antes de abrir tu Pull Request:
   ```bash
   python -m unittest discover -s tests -v
   ```
6. Abre un **Pull Request** describiendo el problema resuelto, los cambios realizados y cómo probarlos.
