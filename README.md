# Streamlit - Mapa de Infraestructura

Archivo de ejemplo para lanzar la aplicación interactiva de plantas y líneas.

Requisitos:

- Python 3.8+
- Instalar dependencias:

```bash
python -m pip install -r requirements.txt
```

Ejecutar la app:

```bash
streamlit run streamlit_app.py
```

Notas:
- Por defecto la aplicación intenta leer los shapefiles dentro de la carpeta `Electricidad` del workspace. Ajusta las rutas en la barra lateral si tus archivos están en otra ubicación.
- La app crea una columna `permiso_tipo` extrayendo el penúltimo segmento de `permis_cre` (ej. `E/1503/AUT/2015` → `AUT`).
- Si tus columnas tienen nombres diferentes para tecnología o capacidad, actualiza `streamlit_app.py` o rellena las rutas y filtros en la interfaz.
