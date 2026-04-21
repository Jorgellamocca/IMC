import os
import json
import streamlit as st
import folium
from shapely.geometry import shape, Point
from streamlit_folium import st_folium

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(page_title="SENAMHI PERÚ", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

LAYER_PATHS = {
    "departamentos": os.path.join(DATA_DIR, "departamentos.geojson"),
    "provincias": os.path.join(DATA_DIR, "provincias.geojson"),
    "cuencas": os.path.join(DATA_DIR, "cuencas.geojson"),
}

VALID_VARIABLES = {"pr", "tasmax", "tasmin"}
VALID_ESTACIONES = {"def", "mam", "jja", "son", "annual", "anual"}

variables_dict = {
    "pr": "Cambio relativo de la precipitación (%)",
    "tasmax": "Cambio proyectado de la temperatura máxima (°C)",
    "tasmin": "Cambio proyectado de la temperatura mínima (°C)"
}

estaciones_dict = {
    "annual": "Anual",
    "def": "Verano (DJF)",
    "mam": "Otoño (MAM)",
    "jja": "Invierno (JJA)",
    "son": "Primavera (SON)"
}

indice_dict = {
    "agricola": "Agricultura",
    "electrica": "Electricidad",
    "vivienda": "Vivienda",
    "mineria": "Minería",
    "salud": "Salud",
    "cultura": "Cultura"
}

prec_colors = [
    "#663300", "#7b4d1b", "#916836", "#a68351", "#bc9d6d", "#d2b888", "#e7d3a3",
    "#c1f4db", "#a1d4bf", "#80b3a3", "#609387", "#40736b", "#20534f", "#003333"
]

temp_colors = [
    "#ffffcc", "#fff7b9", "#fff0a7", "#ffe895", "#fee983", "#fed572", "#fec460",
    "#feb44e", "#fea446", "#fd953f", "#fd8038", "#fc6531", "#fb4b29", "#f03523",
    "#e61f1d", "#d7121f", "#c70723", "#b30026", "#9a0026", "#800026"
]

# =========================================================
# HELPERS
# =========================================================
def normalize_estacion(value: str) -> str:
    v = str(value).strip().lower()
    return "annual" if v == "anual" else v


def parse_climate_filename(filename: str):
    if not filename.endswith(".geojson"):
        return None

    if filename.lower() in {"departamentos.geojson", "provincias.geojson", "cuencas.geojson"}:
        return None

    name = filename[:-8]
    parts = name.split("_")

    if len(parts) < 8:
        return None
    if parts[0].lower() != "distritos":
        return None
    if parts[1].lower() != "cambio":
        return None

    variable = parts[2].lower()
    estacion = normalize_estacion(parts[3])
    escenario = parts[4].lower()
    periodo = f"{parts[5]}_{parts[6]}"

    if variable not in VALID_VARIABLES:
        return None
    if estacion not in VALID_ESTACIONES:
        return None
    if escenario != "cmip6":
        return None

    return {
        "filename": filename,
        "variable": variable,
        "estacion": estacion,
        "periodo": periodo,
    }


def parse_indice_filename(filename: str):
    if not filename.endswith(".geojson"):
        return None

    name = filename[:-8]
    parts = name.split("_")

    if len(parts) < 5:
        return None
    if parts[0].lower() != "indice" or parts[1].lower() != "multipeligro":
        return None

    tipo = parts[2].lower()
    periodo = f"{parts[3]}_{parts[4]}"

    return {
        "filename": filename,
        "tipo": tipo,
        "periodo": periodo,
    }


@st.cache_data(show_spinner=False)
def build_indexes():
    climate_index = {}
    indice_index = {}
    variables = set()
    estaciones = set()
    periodos = set()
    indices = set()

    if not os.path.isdir(DATA_DIR):
        return {}, {}, [], [], [], []

    for f in os.listdir(DATA_DIR):
        climate = parse_climate_filename(f)
        if climate:
            key = (climate["variable"], climate["estacion"], climate["periodo"])
            climate_index[key] = os.path.join(DATA_DIR, climate["filename"])
            variables.add(climate["variable"])
            estaciones.add(climate["estacion"])
            periodos.add(climate["periodo"])
            continue

        indice = parse_indice_filename(f)
        if indice:
            key = (indice["tipo"], indice["periodo"])
            indice_index[key] = os.path.join(DATA_DIR, indice["filename"])
            indices.add(indice["tipo"])

    variable_order = ["pr", "tasmax", "tasmin"]
    estacion_order = ["annual", "def", "mam", "jja", "son"]
    indice_order = ["agricola", "electrica", "vivienda", "mineria", "salud", "cultura"]

    return (
        climate_index,
        indice_index,
        [v for v in variable_order if v in variables],
        [e for e in estacion_order if e in estaciones],
        sorted(periodos),
        [i for i in indice_order if i in indices]
    )


@st.cache_data(show_spinner=False)
def load_geojson(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_district_field_name(geojson_data):
    candidates = [
        "DISTRITO", "distrito", "NOMBDIST", "nomdist",
        "DIST_NOM", "NOMBRE_DIST", "NOMBRE", "name"
    ]
    features = geojson_data.get("features", [])
    if not features:
        return None

    props = features[0].get("properties", {})
    for c in candidates:
        if c in props:
            return c
    return None


def get_value_field_name(geojson_data):
    candidates = ["valor", "VALOR", "indice", "INDICE", "IMC", "imc", "categoria", "CATEGORIA"]
    features = geojson_data.get("features", [])
    if not features:
        return None

    props = features[0].get("properties", {})
    for c in candidates:
        if c in props:
            return c
    return None


def get_district_name(props):
    candidates = [
        "DISTRITO", "distrito", "NOMBDIST", "nomdist",
        "DIST_NOM", "NOMBRE_DIST", "NOMBRE", "name"
    ]
    for c in candidates:
        if c in props and props[c] not in [None, ""]:
            return str(props[c]).strip().upper()
    return "SIN DATO"


def get_valor_field(props):
    candidates = ["valor", "VALOR", "indice", "INDICE", "IMC", "imc", "categoria", "CATEGORIA"]
    for c in candidates:
        if c in props and props[c] not in [None, ""]:
            return props[c]
    return None


def get_climate_color(value, variable):
    if value is None:
        return "#cccccc"

    try:
        value = float(value)
    except Exception:
        return "#cccccc"

    if variable == "pr":
        bins = [-999, -90, -75, -60, -45, -30, -15, 0, 15, 30, 45, 60, 75, 90, 999]
        colors = prec_colors
    else:
        bins = [-999, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2,
                2.4, 2.6, 2.8, 3.0, 3.2, 3.4, 3.6, 3.8, 999]
        colors = temp_colors

    for i in range(len(bins) - 1):
        if bins[i] < value <= bins[i + 1]:
            return colors[i]

    return "#cccccc"


def get_indice_color(raw):
    if raw is None:
        return "#cccccc"

    try:
        val = float(raw)
    except Exception:
        txt = str(raw).lower()
        if "muy" in txt:
            return "#d7191c"
        if "alto" in txt:
            return "#f7941d"
        if "medio" in txt:
            return "#f1dd00"
        if "bajo" in txt:
            return "#9bc68b"
        return "#cccccc"

    if val >= 0.75:
        return "#d7191c"
    if val >= 0.5:
        return "#f7941d"
    if val >= 0.25:
        return "#f1dd00"
    return "#9bc68b"


def climate_style_function(variable):
    def _style(feature):
        props = feature.get("properties", {})
        value = get_valor_field(props)
        return {
            "fillColor": get_climate_color(value, variable),
            "color": "#666666",
            "weight": 0.35,
            "fillOpacity": 0.85
        }
    return _style


def indice_style_function(feature):
    props = feature.get("properties", {})
    raw = get_valor_field(props)
    return {
        "fillColor": get_indice_color(raw),
        "color": "#5e005e",
        "weight": 0.6,
        "fillOpacity": 0.8
    }


def layer_style_function(feature):
    return {
        "color": "#000000",
        "weight": 0.8,
        "fillOpacity": 0.0
    }


def parse_coordinates(lat_text, lon_text):
    try:
        lat = float(str(lat_text).strip().replace(",", "."))
        lon = float(str(lon_text).strip().replace(",", "."))
    except Exception:
        return None, None, "Latitud o longitud no válidas."

    if not (-90 <= lat <= 90):
        return None, None, "La latitud debe estar entre -90 y 90."

    if not (-180 <= lon <= 180):
        return None, None, "La longitud debe estar entre -180 y 180."

    return lat, lon, None


def point_query_feature(geojson_data, lat, lon):
    pt = Point(lon, lat)

    for feature in geojson_data.get("features", []):
        geom = feature.get("geometry")
        if not geom:
            continue

        try:
            polygon = shape(geom)
            if polygon.contains(pt) or polygon.touches(pt):
                return feature.get("properties", {})
        except Exception:
            continue

    return None


def format_value_for_popup(raw, variable=None, is_indice=False):
    if raw in [None, ""]:
        return "Sin dato"

    try:
        val = float(raw)
        if is_indice:
            return f"{val:.2f}"
        if variable == "pr":
            return f"{val:.1f} %"
        return f"{val:.1f} °C"
    except Exception:
        return str(raw)


def build_search_popup_html(
    lat,
    lon,
    climate_props=None,
    variable=None,
    estacion=None,
    periodo=None,
    indice_props=None,
    tipo_indice=None
):
    rows = []
    rows.append(("Latitud", f"{lat:.5f}"))
    rows.append(("Longitud", f"{lon:.5f}"))

    if climate_props is not None:
        distrito = get_district_name(climate_props)
        valor = get_valor_field(climate_props)

        rows.append(("Distrito", distrito))
        rows.append(("Visualización", "Escenario climático"))
        rows.append(("Variable", variables_dict.get(variable, variable)))
        rows.append(("Estación", estaciones_dict.get(estacion, estacion)))
        rows.append(("Período", periodo))
        rows.append(("Valor", format_value_for_popup(valor, variable=variable, is_indice=False)))

    if indice_props is not None:
        distrito_imc = get_district_name(indice_props)
        valor_imc = get_valor_field(indice_props)

        if climate_props is None:
            rows.append(("Distrito", distrito_imc))

        rows.append(("Visualización", "Índice multipeligro"))
        rows.append(("Tipo IMC", indice_dict.get(tipo_indice, tipo_indice)))
        rows.append(("Período IMC", periodo))
        rows.append(("Valor IMC", format_value_for_popup(valor_imc, is_indice=True)))

    if climate_props is None and indice_props is None:
        rows.append(("Resultado", "El punto no cae dentro de un polígono con datos."))

    html_rows = ""
    for k, v in rows:
        html_rows += f"""
        <tr>
            <td style="padding:6px 8px; border:1px solid #ddd; background:#f7f7f7; font-weight:bold;">{k}</td>
            <td style="padding:6px 8px; border:1px solid #ddd;">{v}</td>
        </tr>
        """

    html = f"""
    <div style="width:320px; font-size:12px;">
        <div style="font-weight:bold; margin-bottom:8px; font-size:13px;">
            Información del punto consultado
        </div>
        <table style="border-collapse:collapse; width:100%;">
            {html_rows}
        </table>
    </div>
    """
    return html


# =========================================================
# LEYENDAS
# =========================================================
def add_climate_legend(map_obj, variable):
    if variable == "pr":
        labels = [
            "<= -90", "-90 a -75", "-75 a -60", "-60 a -45", "-45 a -30",
            "-30 a -15", "-15 a 0", "0 a 15", "15 a 30", "30 a 45",
            "45 a 60", "60 a 75", "75 a 90", ">= 90"
        ]
        colors = prec_colors
        title = "Δ P (%)"
    else:
        labels = [
            "<= 0.2", "0.2 a 0.4", "0.4 a 0.6", "0.6 a 0.8", "0.8 a 1.0",
            "1.0 a 1.2", "1.2 a 1.4", "1.4 a 1.6", "1.6 a 1.8", "1.8 a 2.0",
            "2.0 a 2.2", "2.2 a 2.4", "2.4 a 2.6", "2.6 a 2.8", "2.8 a 3.0",
            "3.0 a 3.2", "3.2 a 3.4", "3.4 a 3.6", "3.6 a 3.8", ">= 3.8"
        ]
        colors = temp_colors
        title = "Δ T (°C)"

    items_html = ""
    for c, lab in zip(colors, labels):
        items_html += f"""
        <div style="display:flex; align-items:center; margin-bottom:4px;">
            <span style="
                display:inline-block;
                width:14px;
                height:12px;
                background:{c};
                border:1px solid #999;
                margin-right:6px;">
            </span>
            <span style="font-size:12px;">{lab}</span>
        </div>
        """

    html = f"""
    <div style="
        position: fixed;
        bottom: 25px;
        left: 25px;
        z-index: 999999;
        background: rgba(255,255,255,0.96);
        border: 1px solid #999;
        border-radius: 8px;
        padding: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.25);
        max-height: 280px;
        overflow-y: auto;
        min-width: 160px;
        font-family: Arial, sans-serif;
    ">
        <div style="font-weight:bold; margin-bottom:8px; font-size:13px;">
            {title}
        </div>
        {items_html}
    </div>
    """
    map_obj.get_root().html.add_child(folium.Element(html))


def add_indice_legend(map_obj):
    html = """
    <div style="
        position: fixed;
        bottom: 25px;
        left: 25px;
        z-index: 999999;
        background: rgba(255,255,255,0.96);
        border: 1px solid #999;
        border-radius: 8px;
        padding: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.25);
        max-width: 360px;
        font-family: Arial, sans-serif;
        max-height: 320px;
        overflow-y: auto;
    ">
        <div style="font-weight:bold; margin-bottom:10px; font-size:13px;">
            Índice Multipeligro Climático (IMC)
        </div>

        <div style="font-size:12px; margin-bottom:10px; line-height:1.35;">
            <span style="display:inline-block;width:12px;height:12px;background:#d7191c;border:1px solid #999;margin-right:6px;vertical-align:middle;"></span>
            <b>Muy Alto (0.75 - 1.00):</b> alta concentración y coincidencia de peligros climáticos,
            con mayor probabilidad de impactos severos en el territorio.
        </div>

        <div style="font-size:12px; margin-bottom:10px; line-height:1.35;">
            <span style="display:inline-block;width:12px;height:12px;background:#f7941d;border:1px solid #999;margin-right:6px;vertical-align:middle;"></span>
            <b>Alto (0.50 - 0.75):</b> presencia importante de peligros climáticos,
            con potencial de generar impactos significativos.
        </div>

        <div style="font-size:12px; margin-bottom:10px; line-height:1.35;">
            <span style="display:inline-block;width:12px;height:12px;background:#f1dd00;border:1px solid #999;margin-right:6px;vertical-align:middle;"></span>
            <b>Medio (0.25 - 0.50):</b> presencia moderada de peligros climáticos,
            con impactos posibles según las condiciones del territorio.
        </div>

        <div style="font-size:12px; line-height:1.35;">
            <span style="display:inline-block;width:12px;height:12px;background:#9bc68b;border:1px solid #999;margin-right:6px;vertical-align:middle;"></span>
            <b>Bajo (0.00 - 0.25):</b> menor presencia relativa de peligros climáticos
            y menor probabilidad de impactos severos.
        </div>
    </div>
    """
    map_obj.get_root().html.add_child(folium.Element(html))


# =========================================================
# CAPAS
# =========================================================
def add_climate_layer(map_obj, geojson_data, variable, layer_name):
    district_field = get_district_field_name(geojson_data)
    value_field = get_value_field_name(geojson_data)

    if district_field is None or value_field is None:
        return

    alias_val = "ΔP (%):" if variable == "pr" else "ΔT (°C):"

    folium.GeoJson(
        geojson_data,
        name=layer_name,
        style_function=climate_style_function(variable),
        highlight_function=lambda f: {
            "weight": 1.0,
            "color": "#111111",
            "fillOpacity": 0.95
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[district_field, value_field],
            aliases=["Distrito:", alias_val],
            sticky=True,
            labels=True,
            localize=True
        ),
        popup=folium.GeoJsonPopup(
            fields=[district_field, value_field],
            aliases=["Distrito:", alias_val],
            labels=True,
            localize=True
        ),
    ).add_to(map_obj)


def add_indice_layer(map_obj, geojson_data, layer_name):
    district_field = get_district_field_name(geojson_data)
    value_field = get_value_field_name(geojson_data)

    if district_field is None or value_field is None:
        return

    folium.GeoJson(
        geojson_data,
        name=layer_name,
        style_function=indice_style_function,
        highlight_function=lambda f: {
            "weight": 1.1,
            "color": "#111111",
            "fillOpacity": 0.92
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[district_field, value_field],
            aliases=["Distrito:", "IMC:"],
            sticky=True,
            labels=True,
            localize=True
        ),
        popup=folium.GeoJsonPopup(
            fields=[district_field, value_field],
            aliases=["Distrito:", "IMC:"],
            labels=True,
            localize=True
        ),
    ).add_to(map_obj)


def add_reference_layer(map_obj, geojson_data, name):
    folium.GeoJson(
        geojson_data,
        name=name,
        style_function=layer_style_function,
        control=True,
        overlay=True,
        show=True,
        interactive=False
    ).add_to(map_obj)


# =========================================================
# INDEXES
# =========================================================
(
    climate_index,
    indice_index,
    variables,
    estaciones,
    periodos,
    indices
) = build_indexes()

# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.title("Configuración")

if not periodos:
    st.error("No se encontraron archivos en la carpeta data.")
    st.stop()

periodo = st.sidebar.selectbox("Periodo", periodos, index=0)

variable = st.sidebar.selectbox(
    "Variable",
    variables,
    format_func=lambda x: variables_dict.get(x, x),
    index=0
)

estacion = st.sidebar.selectbox(
    "Estación",
    estaciones,
    format_func=lambda x: estaciones_dict.get(x, x),
    index=0
)

usar_indice = st.sidebar.selectbox(
    "Índice multipeligro climático (IMC)",
    ["No", "Sí"],
    index=0
)

tipo_indice = None
if usar_indice == "Sí":
    tipo_indice = st.sidebar.selectbox(
        "Tipo de índice",
        indices,
        format_func=lambda x: indice_dict.get(x, x),
        index=0
    )

st.sidebar.subheader("Capas de referencia")
show_departamentos = st.sidebar.checkbox("Departamentos", value=False)
show_provincias = st.sidebar.checkbox("Provincias", value=False)
show_cuencas = st.sidebar.checkbox("Cuencas", value=False)

st.sidebar.subheader("Buscar ubicación por coordenadas")
usar_busqueda = st.sidebar.checkbox("Ir a una coordenada", value=False)

lat_input = None
lon_input = None
buscar_punto = False

if usar_busqueda:
    lat_input = st.sidebar.text_input("Latitud", value="-12.0464")
    lon_input = st.sidebar.text_input("Longitud", value="-77.0428")
    buscar_punto = st.sidebar.button("Buscar ubicación")

# =========================================================
# CARGA DE DATOS TEMÁTICOS
# =========================================================
climate_data = None
indice_data = None

climate_key = (variable, estacion, periodo)
climate_path = climate_index.get(climate_key)
if climate_path and os.path.exists(climate_path):
    climate_data = load_geojson(climate_path)

if usar_indice == "Sí":
    indice_key = (tipo_indice, periodo)
    indice_path = indice_index.get(indice_key)
    if indice_path and os.path.exists(indice_path):
        indice_data = load_geojson(indice_path)

# =========================================================
# MAPA: CENTRO DINÁMICO
# =========================================================
map_center = [-9, -75]
map_zoom = 5
search_marker = None
search_popup_html = None

if usar_busqueda and buscar_punto:
    lat, lon, coord_error = parse_coordinates(lat_input, lon_input)

    if coord_error:
        st.sidebar.error(coord_error)
    else:
        map_center = [lat, lon]
        map_zoom = 11
        search_marker = [lat, lon]

        climate_props = None
        indice_props = None

        if climate_data is not None:
            climate_props = point_query_feature(climate_data, lat, lon)

        if indice_data is not None:
            indice_props = point_query_feature(indice_data, lat, lon)

        search_popup_html = build_search_popup_html(
            lat=lat,
            lon=lon,
            climate_props=climate_props,
            variable=variable,
            estacion=estacion,
            periodo=periodo,
            indice_props=indice_props,
            tipo_indice=tipo_indice
        )

# =========================================================
# MAPA
# =========================================================
m = folium.Map(
    location=map_center,
    zoom_start=map_zoom,
    tiles="OpenStreetMap",
    control_scale=True,
    prefer_canvas=True
)

if search_marker is not None:
    folium.Marker(
        location=search_marker,
        popup=folium.Popup(search_popup_html, max_width=380),
        tooltip="Punto consultado",
        icon=folium.Icon(color="red", icon="map-marker", prefix="fa")
    ).add_to(m)

    folium.CircleMarker(
        location=search_marker,
        radius=7,
        color="red",
        fill=True,
        fill_color="red",
        fill_opacity=0.75
    ).add_to(m)

# capa temática principal + leyenda
if usar_indice == "Sí":
    if indice_data is not None:
        add_indice_layer(m, indice_data, layer_name="Índice multipeligro")
        add_indice_legend(m)
    else:
        st.warning("No existe archivo de IMC para la combinación seleccionada.")
else:
    if climate_data is not None:
        add_climate_layer(m, climate_data, variable=variable, layer_name="Capa climática")
        add_climate_legend(m, variable)
    else:
        st.warning("No existe archivo para la combinación seleccionada.")

# capas de referencia
if show_departamentos and os.path.exists(LAYER_PATHS["departamentos"]):
    deptos = load_geojson(LAYER_PATHS["departamentos"])
    add_reference_layer(m, deptos, "Departamentos")

if show_provincias and os.path.exists(LAYER_PATHS["provincias"]):
    provs = load_geojson(LAYER_PATHS["provincias"])
    add_reference_layer(m, provs, "Provincias")

if show_cuencas and os.path.exists(LAYER_PATHS["cuencas"]):
    cuencas = load_geojson(LAYER_PATHS["cuencas"])
    add_reference_layer(m, cuencas, "Cuencas")

folium.LayerControl(collapsed=False).add_to(m)

# =========================================================
# UI
# =========================================================
st.title("SENAMHI PERÚ")

st_folium(
    m,
    width=None,
    height=720,
    returned_objects=[]
)