import os
import re
from typing import Optional
import geopandas as gpd
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import folium
from branca.element import Element
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from shapely import wkt
from shapely.geometry import Point


TECH_MAPPING = {
    "fotovoltaica": "Fotovoltaica",
    "eolico": "Eólico",
    "ciclo combinado": "Ciclo Combinado",
    "turbina hidraulica": "Turbina Hidráulica",
    "termica y combustion": "Térmica y combustión",
    "geotermica": "Geotérmica",
    "nucleoelectrica": "Nucleoeléctrica",
    "carboelectrica": "Carboelectrica",
}


@st.cache_data
def load_and_process_plants(plants_path: str):
    """Load and prepare plant data with all derived columns."""
    gdf = gpd.read_file(plants_path, encoding="utf-8")
    
    # Create a normalized modality column from the requested field
    if "modalidad" in gdf.columns:
        gdf["modalidad_norm"] = gdf["modalidad"].apply(normalize_modalidad)
    else:
        gdf["modalidad_norm"] = None
    
    # Detect and create technology column, preferring tecno_simp
    tech_col = detect_column(gdf, ["tecno_simp", "energet_pr", "tecnologia", "tec", "technology"])
    if tech_col is None:
        gdf["technology"] = "Other"
        tech_col = "technology"

    # Create grouped technology using the requested canonical categories
    gdf["group_tech"] = gdf[tech_col].fillna("").astype(str)
    gdf["group_tech"] = gdf["group_tech"].apply(normalize_tech).map(
        lambda x: TECH_MAPPING.get(x, "Other")
    )
    
    return gdf, tech_col


@st.cache_data
def load_transmission_lines(lines_path: str):
    """Load transmission lines data."""
    return gpd.read_file(lines_path, encoding="utf-8")


@st.cache_data
def load_pasos_fronterizos(path: str):
    """Load pasos fronterizos data."""
    try:
        gdf = gpd.read_file(path, encoding='utf-8')
        return gdf
    except:
        try:
            gdf = gpd.read_file(path, encoding='latin-1')
            return gdf
        except Exception as e:
            st.error(f"Error loading pasos fronterizos: {e}")
            return None


@st.cache_data
def load_gnl_terminals(path: str):
    """Load GNL terminals data."""
    try:
        gdf = gpd.read_file(path, encoding='utf-8')
        return gdf
    except:
        try:
            gdf = gpd.read_file(path, encoding='latin-1')
            return gdf
        except Exception as e:
            st.error(f"Error loading GNL terminals: {e}")
            return None


@st.cache_data
def load_sistrangas(path: str):
    """Load SISTRANGAS gas pipelines data."""
    try:
        gdf = gpd.read_file(path)
        return gdf
    except Exception as e:
        st.error(f"Error loading SISTRANGAS: {e}")
        return None


@st.cache_data
def load_gasoductos_privados(path: str):
    """Load private gas pipelines data."""
    try:
        gdf = gpd.read_file(path, encoding='utf-8')
        return gdf
    except:
        try:
            gdf = gpd.read_file(path, encoding='latin-1')
            return gdf
        except Exception as e:
            st.error(f"Error loading gasoductos privados: {e}")
            return None


def normalize_status(value: Optional[str]) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = text.translate(str.maketrans({
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ñ": "n",
    }))
    return text


def parse_wkt_geometry(value):
    if isinstance(value, str):
        try:
            return wkt.loads(value)
        except Exception:
            return None
    return None


def load_cfe_excel(path: str) -> Optional[gpd.GeoDataFrame]:
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_excel(path)
    except Exception:
        try:
            df = pd.read_excel(path, engine='openpyxl')
        except Exception as e:
            st.warning(f"Error cargando datos de CFE desde {path}: {e}")
            return None

    rename_map = {
        "Proyecto": "central",
        "Tecnología": "group_tech",
        "Capacidad": "cap_mw",
        "Empresa": "empresa",
        "Empresa Matriz": "matriz",
        "Modalidad": "modalidad_norm",
        "Entrada en Operación": "fecha_oper",
        "Estado": "nom_ent",
        "geometry": "geometry",
    }

    normalized_rename = {}
    for col in df.columns:
        for source, target in rename_map.items():
            if col.strip().lower() == source.strip().lower():
                normalized_rename[col] = target
                break
    df = df.rename(columns=normalized_rename)

    if "geometry" in df.columns:
        df["geometry"] = df["geometry"].apply(parse_wkt_geometry)

    # If geometry is missing, build it from coordinate columns
    if "geometry" not in df.columns or df["geometry"].isnull().all():
        lat_col = detect_column(df, ["lat", "latitude"])
        lon_col = detect_column(df, ["long", "lng", "longitude"])
        if lat_col and lon_col:
            def build_point(row):
                lat = row[lat_col]
                lon = row[lon_col]
                if pd.isna(lat) or pd.isna(lon):
                    return None
                try:
                    return Point(float(lon), float(lat))
                except Exception:
                    return None
            df["geometry"] = df.apply(build_point, axis=1)

    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

    if "modalidad_norm" in gdf.columns:
        gdf["modalidad_norm"] = gdf["modalidad_norm"].apply(normalize_modalidad)
    if "group_tech" in gdf.columns:
        gdf["group_tech"] = gdf["group_tech"].fillna("").astype(str)
    if "cap_mw" in gdf.columns:
        gdf["cap_mw"] = pd.to_numeric(gdf["cap_mw"], errors="coerce")

    def normalize_fecha_oper(value):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, str):
            text = value.strip()
            return text if text else None
        if isinstance(value, (int, float)) and float(value).is_integer():
            return str(int(value))
        return str(value)

    if "fecha_oper" in gdf.columns:
        gdf["fecha_oper"] = gdf["fecha_oper"].apply(normalize_fecha_oper)
    else:
        gdf["fecha_oper"] = None

    def project_flag(value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return True
        return extract_year_from_date(value) is None

    gdf["is_project"] = gdf["fecha_oper"].apply(project_flag)
    gdf["fase_simp"] = gdf["is_project"].map({True: "En proyecto", False: "En operación"})

    return gdf


def extract_permiso_tipo(val: Optional[str]) -> Optional[str]:
    if not isinstance(val, str):
        return None
    match = re.fullmatch(r"(?:[^/]+/){2}([^/]+)/[^/]+", val.strip())
    if match:
        return match.group(1)
    parts = val.split("/")
    if len(parts) >= 3:
        return parts[2]
    return None

OPERATIONAL_STATUS_TERMS = {"operacion", "operación", "en operacion", "en operación", "operando", "operacional", "operado", "operada", "en servicio", "funcion"}
PROJECT_STATUS_TERMS = {"proyecto", "en proyecto", "plan de expansion", "plan de expansión", "en desarrollo", "desarrollo constructivo", "en desarrollo constructivo", "plan mixto", "esquema mixto", "planeacion", "planeación", "en construccion", "construccion", "construcción", "na"}


def is_operational_status(value: Optional[str]) -> bool:
    norm = normalize_status(value)
    if not norm:
        return False
    if any(term in norm for term in PROJECT_STATUS_TERMS):
        return False
    return any(term in norm for term in OPERATIONAL_STATUS_TERMS)


def is_project_status(value: Optional[str]) -> bool:
    norm = normalize_status(value)
    if not norm:
        return False
    return any(term in norm for term in PROJECT_STATUS_TERMS)


def detect_column(gdf: gpd.GeoDataFrame, candidates):
    for c in candidates:
        if c in gdf.columns:
            return c
    # try case-insensitive
    cols_low = {c.lower(): c for c in gdf.columns}
    for cand in candidates:
        if cand.lower() in cols_low:
            return cols_low[cand.lower()]
    return None


def normalize_modalidad(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    normalized = re.sub(r"\s+", " ", text).strip()
    replacements = {
        "No defenida": "No definida",
        "No Definida": "No definida",
        "Exportacion": "Exportación",
        "Exportación": "Exportación",
        "Importacion": "Importación",
        "Importación": "Importación",
    }
    return replacements.get(normalized, normalized)


def normalize_tech(value: Optional[str]) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip().lower()
    replacements = str.maketrans({"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"})
    return value.translate(replacements)


def extract_year_from_date(date_value):
    """Extract year from various date formats."""
    if date_value is None or (isinstance(date_value, float) and pd.isna(date_value)):
        return None
    
    try:
        # Try to convert to datetime first
        if hasattr(date_value, 'year'):
            return date_value.year
        elif isinstance(date_value, str):
            # Try different date formats
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y']:
                try:
                    return pd.to_datetime(date_value, format=fmt).year
                except:
                    continue
            # If string is just a number, treat as year
            if date_value.isdigit() and len(date_value) == 4:
                return int(date_value)
        elif isinstance(date_value, (int, float)):
            # If it's a number, check if it could be a year
            if 1900 <= date_value <= 2030:
                return int(date_value)
    except:
        pass
    
    return None


COLOR_MAP = {
    "Fotovoltaica": "goldenrod",
    "Eólico": "lightseagreen",
    "Ciclo Combinado": "red",
    "Turbina Hidráulica": "blue",
    "Térmica y combustión": "dimgray",
    "Geotérmica": "salmon",
    "Nucleoeléctrica": "green",
    "Carboelectrica": "black",
    "Turbina Hidraulica": "blue",
}


def tech_color(tech: Optional[str]):
    if tech is None:
        return "#777777"
    normalized = normalize_tech(tech)
    for key, color in COLOR_MAP.items():
        if normalize_tech(key) == normalized:
            return color
    return "#777777"


def format_date_value(value: Optional[object]) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "No disponible"
    if isinstance(value, (int, float)):
        if float(value).is_integer():
            return str(int(value))
        return str(value)
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


def get_node_radius(capacity: Optional[float]) -> int:
    if capacity is None or pd.isna(capacity):
        return 1
    value = float(capacity)
    if value <= 10:
        return 1
    if value <= 100:
        return 5
    if value <= 500:
        return 10
    if value <= 1000:
        return 15
    return 20


def build_map_object(filtered, gdf_lines, cap_col, line_type_col, 
                    layer_low, layer_medium, layer_high,
                    show_pasos, gdf_pasos,
                    show_gnl, gdf_gnl,
                    show_sistrangas, gdf_sistrangas,
                    show_privados, gdf_privados):
    """Build the Folium map object with lighter geometry payloads."""
    if filtered.empty or 'geometry' not in filtered.columns or filtered.geometry.isnull().all():
        # Return empty map if no data
        m = folium.Map(location=[23.6345, -102.5528], zoom_start=5)
    else:
        centroid = filtered.geometry.union_all().centroid
        m = folium.Map(location=[centroid.y, centroid.x], zoom_start=6)

    # Add transmission layers
    if gdf_lines is not None and line_type_col:
        try:
            gdf_lines_4326 = gdf_lines.to_crs(epsg=4326)
        except Exception:
            gdf_lines_4326 = gdf_lines

        def add_layer(name, mask, color):
            geo = gdf_lines_4326[mask].copy()
            if geo.empty:
                return
            
            # Check if 'nombre_lt' column exists
            nombre_col = None
            if 'nombre_lt' in geo.columns:
                nombre_col = 'nombre_lt'
            elif 'NOMBRE_LT' in geo.columns:
                nombre_col = 'NOMBRE_LT'
            elif 'nombre' in geo.columns:
                nombre_col = 'nombre'
            
            try:
                geo["geometry"] = geo["geometry"].simplify(0.001, preserve_topology=True)
            except Exception:
                pass
            
            # Create GeoJson with popup showing line name
            if nombre_col:
                folium.GeoJson(
                    geo.__geo_interface__,
                    name=name,
                    style_function=lambda feat, color=color: {"color": color, "weight": 2},
                    popup=folium.GeoJsonPopup(
                        fields=[nombre_col],
                        aliases=['Línea de Transmisión:'],
                        localize=True,
                        labels=True,
                        style='background-color: white; font-weight: normal;'
                    )
                ).add_to(m)
            else:
                folium.GeoJson(
                    geo.__geo_interface__,
                    name=name,
                    style_function=lambda feat, color=color: {"color": color, "weight": 2},
                ).add_to(m)

        if layer_low:
            add_layer("Transmisión Baja (<162 kV)", gdf_lines_4326[line_type_col] < 162, "blue")
        if layer_medium:
            add_layer("Transmisión Media (162-231 kV)", (gdf_lines_4326[line_type_col] >= 162) & (gdf_lines_4326[line_type_col] < 231), "magenta")
        if layer_high:
            add_layer("Transmisión Alta (>231 kV)", gdf_lines_4326[line_type_col] >= 231, "darkorange")

    # Add plant markers
    if not filtered.empty and 'geometry' in filtered.columns:
        for _, row in filtered.iterrows():
            tech = row.get("group_tech") if "group_tech" in row.index else row.get('energet_pr')
            color = tech_color(str(tech))
            fecha_oper = row.get("fecha_oper") if "fecha_oper" in row.index else None
            fecha_text = format_date_value(fecha_oper)
            modalidad = row.get("modalidad_norm") if "modalidad_norm" in row.index else None
            matriz = row.get("matriz") if "matriz" in row.index else "No disponible"
            popup = folium.Popup(
                f"<b> Central:</b>  {row.get('central')}<br/>"
                f"<b> Tecnologia:</b> {tech}<br/>"
                f"<b> Capacidad MW:</b> {row.get(cap_col)}<br/>"
                f"<b> Empresa:</b> {row.get('empresa')}<br/>"
                f"<b> Empresa Matriz:</b> {matriz}<br/>"
                f"<b> Modalidad:</b> {modalidad}<br/>"
                f"<b> Fecha Entrada en Operación:</b>  {fecha_text}",
                max_width=300,
            )
            geom = row.geometry
            if geom.geom_type == 'Point':
                radius = get_node_radius(row.get(cap_col) if cap_col in row.index else None)
                if row.get('is_project') is True or str(row.get('fase_simp')).strip().lower() == 'en proyecto':
                    # Project plants: render as square markers
                    folium.RegularPolygonMarker(
                        location=[geom.y, geom.x],
                        number_of_sides=4,
                        rotation=45,
                        radius=radius,
                        color=color,
                        weight=2,
                        fill=True,
                        fill_color=color,
                        popup=popup,
                        fill_opacity=0.7
                    ).add_to(m)
                else:
                    # Operational plants: render as circles
                    folium.CircleMarker(
                        location=[geom.y, geom.x],
                        radius=radius,
                        color=color,
                        fill=True,
                        fill_color=color,
                        popup=popup,
                        fill_opacity=0.7
                    ).add_to(m)
            else:
                folium.GeoJson(row.geometry, style_function=lambda f, col=color: {"color": col}, popup=popup).add_to(m)

    # Add Pasos Fronterizos
    if show_pasos and gdf_pasos is not None and not gdf_pasos.empty:
        try:
            pasos_layer = folium.FeatureGroup(name='Pasos Fronterizos', show=True)
            
            # Convert to EPSG:4326 if needed
            if gdf_pasos.crs != 'EPSG:4326':
                gdf_pasos = gdf_pasos.to_crs(epsg=4326)
            
            for idx, row in gdf_pasos.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    folium.CircleMarker(
                        location=[row.geometry.y, row.geometry.x],
                        radius=max(float(row.get('ImpMex2023', 0)) * 0.01, 5),
                        color='blue',
                        fill=True,
                        fill_color='blue',
                        fill_opacity=0.6,
                        popup=folium.Popup(
                            f"<b>Empresa:</b> {row.get('Emrpesa', 'N/A')}<br>"
                            f"<b>Localidad (Méx):</b> {row.get('Loc_Mex', 'N/A')}<br>"
                            f"<b>Año Operación:</b> {row.get('ano', 'N/A')}<br>"
                            f"<b>Diámetro (\"):</b> {row.get('Diam_Pulg', 'N/A')}<br>"
                            f"<b>Capacidad (MMpcd):</b> {row.get('Vol_MMpcd', 'N/A')}<br>"
                            f"<b>Permiso:</b> {row.get('Permiso', 'N/A')}<br>"
                            f"<b>Tipo de Permiso:</b> {row.get('Tipo_perm', 'N/A')}<br>"
                            f"<b>Importe 2023:</b> {row.get('ImpMex2023', 'N/A')}",
                            max_width=300,
                        ),
                    ).add_to(pasos_layer)
            pasos_layer.add_to(m)
        except Exception as e:
            st.warning(f"Error al agregar Pasos Fronterizos: {e}")

    # Add GNL Terminals
    if show_gnl and gdf_gnl is not None and not gdf_gnl.empty:
        try:
            gdf_gnl_filtered = gdf_gnl.copy()
            if 'Estatus' in gdf_gnl_filtered.columns:
                gdf_gnl_filtered['Estatus_norm'] = gdf_gnl_filtered['Estatus'].astype(str).apply(normalize_status)
                gdf_gnl_filtered = gdf_gnl_filtered[gdf_gnl_filtered['Estatus_norm'].apply(is_operational_status)]
            
            if not gdf_gnl_filtered.empty:
                # Convert to EPSG:4326 if needed
                if gdf_gnl_filtered.crs != 'EPSG:4326':
                    gdf_gnl_filtered = gdf_gnl_filtered.to_crs(epsg=4326)

                gnl_layer_oper = folium.FeatureGroup(name='Terminales GNL (Operación)', show=True)
                geojson_oper = gdf_gnl_filtered.to_json()
                folium.GeoJson(
                    geojson_oper,
                    name='Terminales GNL (Operación)',
                    style_function=lambda feature: {
                        'fillColor': 'orange',
                        'color': 'darkorange',
                        'weight': 2,
                        'fillOpacity': 0.5
                    },
                    tooltip=folium.GeoJsonTooltip(
                        fields=['Terminal'], 
                        aliases=['Terminal:'],
                        style='background-color: white; color: black;'
                    ),
                    popup=folium.GeoJsonPopup(
                        fields=['Terminal', 'Emp_Matriz', 'Estatus', 'ImpExp', 'Ao_Ope', 
                                'Cap_Bcfd', 'Cap_Mtpa', 'Alm_Mm3', 'PermisoCRE'],
                        aliases=['Terminal:', 'Empresa Matriz:', 'Estatus:', 'Import/Export:', 
                                 'Año Operación:', 'Capacidad (Bcfd):', 'Capacidad (Mtpa):', 
                                 'Almacenamiento (Mm3):', 'Permiso CRE:'],
                        localize=True,
                        labels=True,
                        style='background-color: yellow;'
                    )
                ).add_to(gnl_layer_oper)
                gnl_layer_oper.add_to(m)
        except Exception as e:
            st.warning(f"Error al agregar Terminales GNL: {e}")

    # Add SISTRANGAS (only tooltip, no popup)
    if show_sistrangas and gdf_sistrangas is not None and not gdf_sistrangas.empty:
        try:
            sistrangas_layer = folium.FeatureGroup(name='Sistrangas', show=True)
            
            # Convert to EPSG:4326 if needed
            if gdf_sistrangas.crs != 'EPSG:4326':
                gdf_sistrangas = gdf_sistrangas.to_crs(epsg=4326)
            
            gdf_sistrangas_copy = gdf_sistrangas.copy()
            gdf_sistrangas_copy['Sistema'] = 'Sistrangas'
            
            folium.GeoJson(
                gdf_sistrangas_copy.to_json(),
                name='Sistrangas',
                style_function=lambda feature: {
                    'color': 'red',
                    'weight': 2,
                    'opacity': 1
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=['Sistema'],
                    aliases=['Sistema: '],
                    style='background-color: white; color: black;'
                )
            ).add_to(sistrangas_layer)
            sistrangas_layer.add_to(m)
        except Exception as e:
            st.warning(f"Error al agregar Sistrangas: {e}")

    # Add Gasoductos Privados
    if show_privados and gdf_privados is not None and not gdf_privados.empty:
        try:
            # Convert to EPSG:4326 if needed
            if gdf_privados.crs != 'EPSG:4326':
                gdf_privados = gdf_privados.to_crs(epsg=4326)
            
            # Normalize status values
            if 'Estatus' in gdf_privados.columns:
                gdf_privados['estatus_norm'] = gdf_privados['Estatus'].astype(str).apply(normalize_status)
                gdf_proyecto = gdf_privados[gdf_privados['estatus_norm'].apply(is_project_status)]
                gdf_operacion = gdf_privados[~gdf_privados.index.isin(gdf_proyecto.index)]
            else:
                gdf_operacion = gdf_privados.copy()
                gdf_proyecto = gpd.GeoDataFrame(columns=gdf_privados.columns)

            privados_layer = folium.FeatureGroup(name='Gasoductos Privados', show=True)

            if not gdf_operacion.empty:
                folium.GeoJson(
                    gdf_operacion.to_json(),
                    name='En Operación',
                    style_function=lambda feature: {
                        'color': 'blue',
                        'weight': 3,
                        'opacity': 1
                    },
                    tooltip=folium.GeoJsonTooltip(
                        fields=['Nombre'],
                        aliases=['Nombre: '],
                        style='background-color: white; color: black; font-weight: normal;'
                    ),
                    popup=folium.GeoJsonPopup(
                        fields=['Nombre', 'Emp_Matriz', 'Estatus', 'Ao_Constr', 
                            'Ao_Operac', 'Diametro', 'Longitud', 'Cap_mmpc', 'Permiso'],
                        aliases=['Nombre:', 'Empresa Matriz:', 'Estatus:', 'Año Construcción:',
                                'Año Operación:', 'Diámetro:', 'Longitud:', 'Capacidad (mmpc):', 'Permiso:'],
                        localize=True,
                        labels=True,
                        style='background-color: white; font-weight: normal;',
                        max_width=300
                    )
                ).add_to(privados_layer)

            if not gdf_proyecto.empty:
                folium.GeoJson(
                    gdf_proyecto.to_json(),
                    name='En Proyecto',
                    style_function=lambda feature: {
                        'color': 'blue',
                        'weight': 2,
                        'opacity': 0.7,
                        'dashArray': '5, 5'
                    },
                    tooltip=folium.GeoJsonTooltip(
                        fields=['Nombre'],
                        aliases=['Nombre (Proyecto): '],
                        style='background-color: white; color: black; font-weight: normal;'
                    ),
                    popup=folium.GeoJsonPopup(
                        fields=['Nombre', 'Emp_Matriz', 'Estatus', 'Ao_Constr', 
                            'Ao_Operac', 'Diametro', 'Longitud', 'Cap_mmpc', 'Permiso'],
                        aliases=['Nombre:', 'Empresa Matriz:', 'Estatus:', 'Año Construcción:',
                                'Año Operación:', 'Diámetro:', 'Longitud:', 'Capacidad (mmpc):', 'Permiso:'],
                        localize=True,
                        labels=True,
                        style='background-color: white; font-weight: normal;',
                        max_width=300
                    )
                ).add_to(privados_layer)

            privados_layer.add_to(m)
        except Exception as e:
            st.warning(f"Error al agregar Gasoductos Privados: {e}")

    # Add legend overlay for circle size and project triangle
    legend_html = '''
    <div style="position: absolute; bottom: 10px; left: 10px; z-index:9999; background: rgba(255,255,255,0.95); padding: 10px; border-radius: 8px; box-shadow: 2px 2px 8px rgba(0,0,0,0.15); font-size: 12px;">
        <div style="font-weight: bold; margin-bottom: 6px;">Leyenda de Iconos</div>
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#777;"></span>1-10 MW</div>
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;"><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#777;"></span>10-100 MW</div>
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;"><span style="display:inline-block;width:16px;height:16px;border-radius:50%;background:#777;"></span>100-500 MW</div>
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;"><span style="display:inline-block;width:20px;height:20px;border-radius:50%;background:#777;"></span>>500 MW</div>
        <div style="display: flex; align-items: center; gap: 8px;"><span style="display:inline-block;width:14px;height:14px;background:#777;border:2px solid #777;"></span>Cuadrado = Planta en proyecto</div>
    </div>
    '''
    m.get_root().html.add_child(Element(legend_html))

    # Add layer control
    folium.LayerControl().add_to(m)
    return m


def create_donut_chart(data, title, value_col='capacity', name_col='technology'):
    """Create a donut chart for capacity breakdown."""
    fig = go.Figure(data=[go.Pie(
        labels=data[name_col], 
        values=data[value_col], 
        hole=.4,
        marker=dict(colors=[tech_color(t) for t in data[name_col]])
    )])
    fig.update_layout(
        title=title,
        showlegend=True,
        height=400
    )
    return fig


def main():
    st.set_page_config(layout="wide", page_title="Infraestructura - Análisis")
    st.title("Sistema Eléctrico Nacional - Análisis de Capacidad")

    # sensible defaults relative to this script's directory
    base_dir = os.path.dirname(__file__)
    default_plants = os.path.join(base_dir, "Electricidad", "Centrales_Electricas_PLANEAS_Feb_2024", "Centrales_Electricas_PLANEAS_Feb_2024.shp")
    default_lines = os.path.join(base_dir, "Electricidad", "LT_Operacion_Abril2024", "LT_Operacion_Abril2024.shp")
    
    # Additional layers paths
    default_pasos = os.path.join(base_dir, "Gas", "Gas_Puntos_Interconexion", "Pasos_fronterizos_gas_metano.shp")
    default_gnl = os.path.join(base_dir, "Gas", "Terminales_GNL", "Terminales_GNL_Mexico.shp")
    default_sistrangas = os.path.join(base_dir, "Gas", "Gasoductos_SISTRANGAS", "gasoductos_sng.shp")
    default_privados = os.path.join(base_dir, "Gas", "Gasoductos_privados", "Gasoductos_privados.shp")

    plants_path = default_plants
    lines_path = default_lines

    if not os.path.exists(plants_path):
        st.warning(f"Archivo plantas no encontrado: {plants_path}")
    if not os.path.exists(lines_path):
        st.warning(f"Archivo líneas no encontrado: {lines_path}")

    # Load cached data
    try:
        if os.path.exists(plants_path):
            gdf_plants, tech_col = load_and_process_plants(plants_path)
        else:
            st.error("Archivo de plantas no encontrado")
            st.stop()
        
        # Load CFE expansion datasets and build four explicit subsets:
        # 1) base operational plants (from shapefile) -> only fase_simp == 'En operación'
        # 2) cfe_plan_expansion with numeric 'fecha_oper' -> CircleMarker
        # 3) cfe_plan_expansion with non-numeric 'fecha_oper' (e.g. '3T 2026') -> Square
        # 4) cfe_esquema_mixto -> Square (Lat/Long -> geometry)

        # keep a copy of the original full plants and extract only operational as the primary subset
        gdf_plants_full = gdf_plants.copy()
        if 'fase_simp' in gdf_plants_full.columns:
            gdf_plants_oper = gdf_plants_full[gdf_plants_full['fase_simp'] == 'En operación'].copy()
        else:
            gdf_plants_oper = gdf_plants_full.copy()

        # Paths
        cfe_plan_path = os.path.join(base_dir, "cfe_plan_expansion.xlsx")
        cfe_mixto_path = os.path.join(base_dir, "cfe_esquema_mixto.xlsx")

        # Prepare containers for the three CFE-derived subsets
        gdf_cfe_plan_numeric = None
        gdf_cfe_plan_string = None
        gdf_cfe_mixto = None

        # Helper to align columns to target
        def align_to_target(gdf_src, target_cols):
            for col in target_cols:
                if col not in gdf_src.columns:
                    gdf_src[col] = None
            # ensure same column order
            return gdf_src[target_cols].copy()

        target_cols = list(gdf_plants_full.columns)

        # Load cfe_plan_expansion and split by whether fecha_oper yields a year
        if os.path.exists(cfe_plan_path):
            gdf_cfe_plan = load_cfe_excel(cfe_plan_path)
            if gdf_cfe_plan is not None and not gdf_cfe_plan.empty:
                # Normalize CRS
                try:
                    if gdf_cfe_plan.crs != gdf_plants_full.crs:
                        gdf_cfe_plan = gdf_cfe_plan.to_crs(gdf_plants_full.crs)
                except Exception:
                    pass

                # Force modality label to include CFE Plan de Expansión so it appears in dropdown
                if 'modalidad_norm' in gdf_cfe_plan.columns:
                    gdf_cfe_plan['modalidad_norm'] = gdf_cfe_plan['modalidad_norm'].apply(lambda v: 'CFE Plan de Expansión' if normalize_modalidad(str(v) or '') in ['plan de expansion', 'plan de expansión', 'plan de expansio', 'plan de expans'] else v)
                else:
                    gdf_cfe_plan['modalidad_norm'] = 'CFE Plan de Expansión'

                # Split numeric vs non-numeric fecha_oper
                def has_numeric_year(val):
                    return extract_year_from_date(val) is not None

                try:
                    mask_numeric = gdf_cfe_plan['fecha_oper'].apply(has_numeric_year)
                except Exception:
                    mask_numeric = pd.Series([False] * len(gdf_cfe_plan), index=gdf_cfe_plan.index)

                gdf_cfe_plan_numeric = gdf_cfe_plan[mask_numeric].copy()
                gdf_cfe_plan_string = gdf_cfe_plan[~mask_numeric].copy()

                # Mark types: numeric -> operational marker (circle), string -> project (triangle)
                if not gdf_cfe_plan_numeric.empty:
                    gdf_cfe_plan_numeric['is_project'] = False
                    gdf_cfe_plan_numeric['fase_simp'] = 'En operación'
                    gdf_cfe_plan_numeric = align_to_target(gdf_cfe_plan_numeric, target_cols)

                if not gdf_cfe_plan_string.empty:
                    gdf_cfe_plan_string['is_project'] = True
                    gdf_cfe_plan_string['fase_simp'] = 'En proyecto'
                    gdf_cfe_plan_string = align_to_target(gdf_cfe_plan_string, target_cols)

        # Load cfe_esquema_mixto and create geometry from Lat/Long if needed
        if os.path.exists(cfe_mixto_path):
            gdf_cfe_m = load_cfe_excel(cfe_mixto_path)
            if gdf_cfe_m is not None and not gdf_cfe_m.empty:
                # If Lat/Long present but geometry missing, build geometry
                if 'geometry' not in gdf_cfe_m.columns or gdf_cfe_m['geometry'].isnull().all():
                    lat_col = detect_column(gdf_cfe_m, ['lat', 'Lat', 'latitude'])
                    lon_col = detect_column(gdf_cfe_m, ['long', 'Long', 'lng', 'longitude'])
                    if lat_col and lon_col:
                        def build_point_m(row):
                            lat = row.get(lat_col)
                            lon = row.get(lon_col)
                            try:
                                if pd.isna(lat) or pd.isna(lon):
                                    return None
                                return Point(float(lon), float(lat))
                            except Exception:
                                return None
                        gdf_cfe_m['geometry'] = gdf_cfe_m.apply(build_point_m, axis=1)

                # Normalize CRS
                try:
                    if gdf_cfe_m.crs != gdf_plants_full.crs:
                        gdf_cfe_m = gdf_cfe_m.to_crs(gdf_plants_full.crs)
                except Exception:
                    pass

                # Force modality label to Esquema Mixto
                gdf_cfe_m['modalidad_norm'] = 'Esquema Mixto'
                gdf_cfe_m['is_project'] = True
                gdf_cfe_m['fase_simp'] = 'En proyecto'

                # Ensure cfe_esquema_mixto rows are not dropped later by missing state.
                if 'nom_ent' not in gdf_cfe_m.columns:
                    gdf_cfe_m['nom_ent'] = None
                if 'Región' in gdf_cfe_m.columns:
                    gdf_cfe_m['nom_ent'] = gdf_cfe_m['nom_ent'].fillna(gdf_cfe_m['Región'])
                gdf_cfe_m['nom_ent'] = gdf_cfe_m['nom_ent'].fillna('No definido')

                gdf_cfe_mixto = align_to_target(gdf_cfe_m, target_cols)

        # Build final plants dataframe used for UI and mapping: operational base + CFE subsets
        parts = [gdf_plants_oper]
        if gdf_cfe_plan_numeric is not None and not gdf_cfe_plan_numeric.empty:
            parts.append(gdf_cfe_plan_numeric)
        if gdf_cfe_plan_string is not None and not gdf_cfe_plan_string.empty:
            parts.append(gdf_cfe_plan_string)
        if gdf_cfe_mixto is not None and not gdf_cfe_mixto.empty:
            parts.append(gdf_cfe_mixto)

        if len(parts) > 1:
            try:
                gdf_plants = pd.concat(parts, ignore_index=True)
            except Exception:
                # fallback: ensure columns align strictly
                aligned = [align_to_target(p, target_cols) for p in parts]
                gdf_plants = pd.concat(aligned, ignore_index=True)
        else:
            gdf_plants = gdf_plants_oper.copy()

        # Ensure the consolidated dataframe has an explicit project flag.
        if 'is_project' not in gdf_plants.columns:
            gdf_plants['is_project'] = gdf_plants['fase_simp'].astype(str).str.lower().str.contains('proyecto', na=False)
        
        if os.path.exists(lines_path):
            gdf_lines = load_transmission_lines(lines_path)
        else:
            gdf_lines = None
            
        # Load additional layers
        gdf_pasos = None
        gdf_gnl = None
        gdf_sistrangas = None
        gdf_privados = None
        
        if os.path.exists(default_pasos):
            gdf_pasos = load_pasos_fronterizos(default_pasos)
        if os.path.exists(default_gnl):
            gdf_gnl = load_gnl_terminals(default_gnl)
        if os.path.exists(default_sistrangas):
            gdf_sistrangas = load_sistrangas(default_sistrangas)
        if os.path.exists(default_privados):
            gdf_privados = load_gasoductos_privados(default_privados)
            
    except Exception as e:
        st.error(f"Error leyendo archivos: {e}")
        st.stop()

    # Detect capacity column
    cap_col = detect_column(gdf_plants, ["cap_mw", "capacidad", "capacidad_mw", "potencia", "mw"]) 
    if cap_col is None:
        numeric_cols = [c for c in gdf_plants.columns if pd.api.types.is_numeric_dtype(gdf_plants[c])]
        cap_col = numeric_cols[0] if numeric_cols else None

    # Create plants subset with key columns
    subset_cols = [c for c in ["central", "empresa", cap_col, "energet_pr", "group_tech", "fase_simp", "modalidad_norm", "fecha_oper", "nom_ent", "matriz", "geometry", "is_project"] if c in gdf_plants.columns]
    gdf_plantas = gdf_plants[subset_cols].copy()
    
    # Keep both operational plants and projects so CFE expansion entries are visible
    # Proyectos tendrán triángulo en el mapa vía is_project

    # Remove null/empty geometries
    if 'geometry' in gdf_plantas.columns:
        gdf_plantas = gdf_plantas[gdf_plantas.geometry.notnull()]
        try:
            gdf_plantas = gdf_plantas[~gdf_plantas.geometry.is_empty]
        except Exception:
            pass

    # Extract year from fecha_oper and add as column
    if 'fecha_oper' in gdf_plantas.columns:
        gdf_plantas['year_oper'] = gdf_plantas['fecha_oper'].apply(extract_year_from_date)
    else:
        gdf_plantas['year_oper'] = None

    if 'is_project' not in gdf_plantas.columns:
        gdf_plantas['is_project'] = gdf_plantas['fase_simp'].astype(str).str.lower().str.contains('proyecto', na=False)

    # Exclude 'Texas' and 'None' from nom_ent if it exists
    if 'nom_ent' in gdf_plantas.columns:
        gdf_plantas = gdf_plantas[~gdf_plantas['nom_ent'].isin(['Texas', 'None'])]
    else:
        st.warning("Column 'nom_ent' not found in the dataset")

    # Create tabs
    tab1, tab2, tab3 = st.tabs(["Mapa Interactivo", "Resumen Nacional", "Resumen por Estado"])
    
    # Tab 1: Map (existing functionality with year filter)
    with tab1:
        st.header("Mapa interactivo - Plantas y Líneas de Transmisión")
        
        # Prepare filter options
        permiso_opts = []
        if "modalidad_norm" in gdf_plantas.columns:
            permiso_opts = sorted([p for p in gdf_plantas["modalidad_norm"].dropna().unique()])
        
        tech_opts = sorted([t for t in gdf_plantas["group_tech"].dropna().unique()]) if "group_tech" in gdf_plantas.columns else ["Other"]
        
        matriz_opts = []
        if "matriz" in gdf_plantas.columns:
            matriz_opts = sorted([m for m in gdf_plantas["matriz"].dropna().unique() if m])

        # Initialize session state for filters
        if "permiso_sel" not in st.session_state:
            st.session_state.permiso_sel = "(Todos)"
        if "tech_sel" not in st.session_state:
            st.session_state.tech_sel = "(Todos)"
        if "matriz_sel" not in st.session_state:
            st.session_state.matriz_sel = "(Todos)"
        if "mw_range" not in st.session_state:
            st.session_state.mw_range = (0, 3000)
        if "selected_year" not in st.session_state:
            st.session_state.selected_year = 2026
        if "layer_low" not in st.session_state:
            st.session_state.layer_low = True
        if "layer_medium" not in st.session_state:
            st.session_state.layer_medium = True
        if "layer_high" not in st.session_state:
            st.session_state.layer_high = True
        if "show_pasos" not in st.session_state:
            st.session_state.show_pasos = False
        if "show_gnl" not in st.session_state:
            st.session_state.show_gnl = False
        if "show_sistrangas" not in st.session_state:
            st.session_state.show_sistrangas = False
        if "show_privados" not in st.session_state:
            st.session_state.show_privados = False
        if "last_filter_state" not in st.session_state:
            st.session_state.last_filter_state = None

        # Sidebar filters
        st.sidebar.markdown("## Filtros del Mapa")
        st.session_state.permiso_sel = st.sidebar.selectbox("Filtrar por tipo de permiso", options=["(Todos)"] + permiso_opts, key="permiso_key")
        st.session_state.tech_sel = st.sidebar.selectbox("Filtrar por tecnología", options=["(Todos)"] + tech_opts, key="tech_key")
        if matriz_opts:
            st.session_state.matriz_sel = st.sidebar.selectbox("Empresa Matriz", options=["(Todos)"] + matriz_opts, key="matriz_key")
        st.session_state.mw_range = st.sidebar.slider("Rango de capacidad (MW)", min_value=0, max_value=3000, value=st.session_state.mw_range, key="mw_key")
        
        # Transmission layers checkboxes
        if gdf_lines is not None:
            st.sidebar.markdown("---")
            st.sidebar.markdown("**Capas de Líneas de Transmisión (por tensión)**")
            st.session_state.layer_low = st.sidebar.checkbox("Low (<162 kV)", value=st.session_state.layer_low, key="layer_low_key")
            st.session_state.layer_medium = st.sidebar.checkbox("Medium (162-231 kV)", value=st.session_state.layer_medium, key="layer_medium_key")
            st.session_state.layer_high = st.sidebar.checkbox("High (>231 kV)", value=st.session_state.layer_high, key="layer_high_key")
            line_type_col = detect_column(gdf_lines, ["tension_kv", "tension", "voltage"]) 
        else:
            line_type_col = None

        # Additional geographic layers
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Capas de Infraestructura de Gas**")
        st.session_state.show_pasos = st.sidebar.checkbox("Pasos Fronterizos", value=st.session_state.show_pasos, key="pasos_key")
        st.session_state.show_gnl = st.sidebar.checkbox("Terminales GNL", value=st.session_state.show_gnl, key="gnl_key")
        st.session_state.show_sistrangas = st.sidebar.checkbox("Sistrangas", value=st.session_state.show_sistrangas, key="sistrangas_key")
        st.session_state.show_privados = st.sidebar.checkbox("Gasoductos Privados", value=st.session_state.show_privados, key="privados_key")

        # Year navigation at the bottom - ONLY buttons, no slider
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Plantas en operación de acuerdo al año n**")
        
        # Year navigation with just two buttons
        col1, col2, col3 = st.sidebar.columns([1, 2, 1])
        
        with col1:
            if st.button("←", key="year_back", help="Año anterior"):
                st.session_state.selected_year = max(1960, st.session_state.selected_year - 1)
                st.rerun()
        
        with col2:
            st.markdown(f"<div style='text-align: center; padding: 10px; font-size: 24px; font-weight: bold; background-color: #f0f2f6; border-radius: 5px;'>{st.session_state.selected_year}</div>", unsafe_allow_html=True)
        
        with col3:
            if st.button("→", key="year_forward", help="Año siguiente"):
                st.session_state.selected_year = min(2026, st.session_state.selected_year + 1)
                st.rerun()

        # Compute current filter state
        current_filter_state = f"{st.session_state.permiso_sel}|{st.session_state.tech_sel}|{st.session_state.matriz_sel}|{st.session_state.mw_range[0]}-{st.session_state.mw_range[1]}|{st.session_state.selected_year}|{st.session_state.layer_low}|{st.session_state.layer_medium}|{st.session_state.layer_high}|{st.session_state.show_pasos}|{st.session_state.show_gnl}|{st.session_state.show_sistrangas}|{st.session_state.show_privados}"

        # Apply filters
        filtered = gdf_plantas.copy()
        if st.session_state.permiso_sel != "(Todos)" and "modalidad_norm" in filtered.columns:
            filtered = filtered[filtered["modalidad_norm"] == st.session_state.permiso_sel]
        if st.session_state.tech_sel != "(Todos)" and "group_tech" in filtered.columns:
            filtered = filtered[filtered["group_tech"] == st.session_state.tech_sel]
        if st.session_state.matriz_sel != "(Todos)" and "matriz" in filtered.columns:
            filtered = filtered[filtered["matriz"] == st.session_state.matriz_sel]
        if cap_col and cap_col in filtered.columns:
            filtered = filtered[(filtered[cap_col].fillna(0) >= st.session_state.mw_range[0]) & (filtered[cap_col].fillna(0) <= st.session_state.mw_range[1])]
        
        # Apply year filter - shows plants that started operation up to the selected year
        if 'year_oper' in filtered.columns:
            year_mask = (
                (filtered['year_oper'].isna()) | 
                (filtered['year_oper'] <= st.session_state.selected_year)
            )
            filtered = filtered[year_mask]

        # Handle empty filtered results
        if filtered.empty or ('geometry' in filtered.columns and filtered.geometry.isnull().all()):
            st.warning(f"No hay plantas en operación hasta el año {st.session_state.selected_year} con los filtros seleccionados.")
            filtered = gdf_plantas.copy()

        # Rebuild the map when the sidebar filters change.
        if st.session_state.last_filter_state != current_filter_state:
            map_obj = build_map_object(
                filtered, gdf_lines, cap_col, line_type_col,
                st.session_state.layer_low, st.session_state.layer_medium, st.session_state.layer_high,
                st.session_state.show_pasos, gdf_pasos,
                st.session_state.show_gnl, gdf_gnl,
                st.session_state.show_sistrangas, gdf_sistrangas,
                st.session_state.show_privados, gdf_privados
            )
            st.session_state.last_filter_state = current_filter_state
        else:
            map_obj = build_map_object(
                filtered, gdf_lines, cap_col, line_type_col,
                st.session_state.layer_low, st.session_state.layer_medium, st.session_state.layer_high,
                st.session_state.show_pasos, gdf_pasos,
                st.session_state.show_gnl, gdf_gnl,
                st.session_state.show_sistrangas, gdf_sistrangas,
                st.session_state.show_privados, gdf_privados
            )

        # Show filter summary
        st.info(f"Mostrando {len(filtered)} plantas en operación hasta el año {st.session_state.selected_year}")
        components.html(map_obj.get_root().render(), height=800, scrolling=False)
        st.caption("Mapa creado por Iván Montenegro. Capas geográficas provenientes de Geocomunes. Datos actualizados hasta 2023. Posteriormente se agregan plantas en proyecto del plan de expansión de CFE y esquema mixto.")
    
    # Tab 2: National Summary
    with tab2:
        st.header("Resumen Nacional del Sistema Eléctrico Nacional")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Donut chart for national capacity breakdown
            national_capacity = gdf_plantas.groupby('group_tech')[cap_col].sum().reset_index()
            national_capacity.columns = ['technology', 'capacity']
            national_capacity = national_capacity[national_capacity['technology'] != 'Other']
            
            fig_donut_national = create_donut_chart(national_capacity, 'Capacidad Nacional por Tecnología')
            st.plotly_chart(fig_donut_national, use_container_width=True)
        
        with col2:
            # Top 10 plants at national level
            st.subheader("Top 10 Plantas por Capacidad")
            top_10_plants = gdf_plantas.nlargest(10, cap_col)[['central', cap_col, 'group_tech', 'nom_ent']]
            top_10_plants.columns = ['Central', 'Capacidad MW', 'Tecnología', 'Estado']
            st.dataframe(top_10_plants, use_container_width=True, hide_index=True)
        
        # Stacked bar chart by state
        st.subheader("Capacidad por Estado y Tecnología")
        
        # Prepare data for stacked bar chart
        state_capacity = gdf_plantas.groupby(['nom_ent', 'group_tech'])[cap_col].sum().unstack(fill_value=0)
        
        # Remove 'Other' column if it exists
        if 'Other' in state_capacity.columns:
            state_capacity = state_capacity.drop('Other', axis=1)
        
        # Sort by total capacity
        state_capacity['Total'] = state_capacity.sum(axis=1)
        state_capacity = state_capacity.sort_values('Total', ascending=False)
        state_capacity = state_capacity.drop('Total', axis=1)
        
        # Create stacked bar chart using graph_objects for better control
        fig_stacked = go.Figure()
        
        for tech in state_capacity.columns:
            fig_stacked.add_trace(go.Bar(
                name=tech,
                x=state_capacity.index,
                y=state_capacity[tech],
                marker_color=tech_color(tech)
            ))
        
        fig_stacked.update_layout(
            barmode='stack',
            title='Capacidad Instalada por Estado y Tecnología',
            xaxis_title='Estado',
            yaxis_title='Capacidad (MW)',
            xaxis_tickangle=-45,
            height=500,
            legend_title='Tecnología'
        )
        
        st.plotly_chart(fig_stacked, use_container_width=True)
        
        # Dropdown for technology-specific state ranking
        st.subheader("Ranking de Estados por Tecnología")
        tech_options = sorted([t for t in gdf_plantas['group_tech'].unique() if t != 'Other'])
        selected_tech = st.selectbox("Seleccionar Tecnología", tech_options, key="tech_ranking")
        
        if selected_tech:
            tech_state_capacity = gdf_plantas[gdf_plantas['group_tech'] == selected_tech].groupby('nom_ent')[cap_col].sum().sort_values(ascending=False).reset_index()
            tech_state_capacity.columns = ['Estado', 'Capacidad (MW)']
            
            fig_tech_ranking = px.bar(
                tech_state_capacity, 
                x='Estado', 
                y='Capacidad (MW)',
                title=f'Capacidad {selected_tech} por Estado',
                color='Capacidad (MW)',
                color_continuous_scale='viridis'
            )
            fig_tech_ranking.update_layout(xaxis_tickangle=-45, height=500)
            st.plotly_chart(fig_tech_ranking, use_container_width=True)
    
    # Tab 3: State Summary
    with tab3:
        st.header("Resumen por Estado")
        
        if 'nom_ent' in gdf_plantas.columns:
            state_options = sorted([s for s in gdf_plantas['nom_ent'].unique() if s not in ['Texas', 'None']])
            selected_state = st.selectbox("Seleccionar Estado", state_options, key="state_selector")
            
            if selected_state:
                state_data = gdf_plantas[gdf_plantas['nom_ent'] == selected_state]
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # Donut chart for state capacity breakdown
                    state_tech_capacity = state_data.groupby('group_tech')[cap_col].sum().reset_index()
                    state_tech_capacity.columns = ['technology', 'capacity']
                    state_tech_capacity = state_tech_capacity[state_tech_capacity['technology'] != 'Other']
                    
                    fig_donut_state = create_donut_chart(state_tech_capacity, f'Capacidad en {selected_state} por Tecnología')
                    st.plotly_chart(fig_donut_state, use_container_width=True)
                
                with col2:
                    # State statistics
                    st.subheader(f"Estadísticas de {selected_state}")
                    total_capacity = state_data[cap_col].sum()
                    num_plants = len(state_data)
                    tech_types = state_data['group_tech'].nunique()
                    
                    col_met1, col_met2, col_met3 = st.columns(3)
                    with col_met1:
                        st.metric("Capacidad Total", f"{total_capacity:.0f} MW")
                    with col_met2:
                        st.metric("Número de Plantas", num_plants)
                    with col_met3:
                        st.metric("Tipos de Tecnología", tech_types)
                
                # 5 newest and 5 oldest plants
                if 'fecha_oper' in state_data.columns:
                    state_data_sorted = state_data.copy()
                    state_data_sorted['fecha_oper_clean'] = pd.to_datetime(state_data_sorted['fecha_oper'], errors='coerce')
                    
                    col_new, col_old = st.columns(2)
                    
                    with col_new:
                        st.subheader("5 Plantas Más Nuevas")
                        newest_plants = state_data_sorted.nlargest(5, 'fecha_oper_clean')[['central', cap_col, 'group_tech', 'fecha_oper']]
                        newest_plants.columns = ['Central', 'Capacidad (MW)', 'Tecnología', 'Fecha Operación']
                        st.dataframe(newest_plants, use_container_width=True, hide_index=True)
                    
                    with col_old:
                        st.subheader("5 Plantas Más Antiguas")
                        oldest_plants = state_data_sorted.nsmallest(5, 'fecha_oper_clean')[['central', cap_col, 'group_tech', 'fecha_oper']]
                        oldest_plants.columns = ['Central', 'Capacidad (MW)', 'Tecnología', 'Fecha Operación']
                        st.dataframe(oldest_plants, use_container_width=True, hide_index=True)
                else:
                    st.warning("No se encontró la columna de fecha de operación")
        else:
            st.error("No se encontró la columna 'nom_ent' en los datos")


if __name__ == "__main__":
    main()