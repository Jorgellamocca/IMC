import os
import json
import geopandas as gpd
import streamlit as st
import folium
from branca.element import MacroElement
from jinja2 import Template
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

    # Excluir capas administrativas
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
    gdf = gpd.read_file(path)

    if gdf.crs is not None and gdf.crs.to_string() != "EPSG:4326":
        gdf = gdf.to_crs(epsg=4326)

    return json.loads(gdf.to_json())


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
        value = props.get("valor")
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


def climate_popup_html(feature, variable):
    props = feature.get("properties", {})
    distrito = get_district_name(props)
    val = props.get("valor")

    if val is None or val == "":
        label = "Sin dato"
    else:
        try:
            if variable == "pr":
                label = f"ΔP: {float(val):.1f}%"
            else:
                label = f"ΔT: {float(val):.1f}°C"
        except Exception:
            label = f"{val}"

    return f"""
    <div style="font-size:13px;">
        <b>DISTRITO:</b> {distrito}<br>
        <b>{label}</b>
    </div>
    """


def indice_popup_html(feature):
    props = feature.get("properties", {})
    distrito = get_district_name(props)
    raw = get_valor_field(props)

    if raw is None or raw == "":
        imc_text = "Sin dato"
    else:
        try:
            imc_text = f"{float(raw):.2f}"
        except Exception:
            imc_text = str(raw)

    return f"""
    <div style="font-size:13px;">
        <b>DISTRITO:</b> {distrito}<br>
        <b>IMC:</b> {imc_text}
    </div>
    """


class FloatLegend(MacroElement):
    def __init__(self, html):
        super().__init__()
        self._name = "FloatLegend"
        self.template = Template(f"""
        {{% macro html(this, kwargs) %}}
        {html}
        {{% endmacro %}}
        """)


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
            <span style="display:inline-block; width:14px; height:12px; background:{c};
                         border:1px solid #999; margin-right:6px;"></span>
            <span style="font-size:12px;">{lab}</span>
        </div>
        """

    html = f"""
    <div style="
        position: fixed;
        bottom: 25px;
        left: 25px;
        z-index: 9999;
        background: rgba(255,255,255,0.95);
        border-radius: 8px;
        padding: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        max-height: 280px;
        overflow-y: auto;
        min-width: 150px;
    ">
        <div style="font-weight:bold; margin-bottom:8px; font-size:13px;">{title}</div>
        {items_html}
    </div>
    """
    map_obj.get_root().add_child(FloatLegend(html))


def add_indice_legend(map_obj):
    html = """
    <div style="
        position: fixed;
        bottom: 25px;
        left: 25px;
        z-index: 9999;
        background: rgba(255,255,255,0.95);
        border-radius: 8px;
        padding: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        max-width: 320px;
    ">
        <div style="font-weight:bold; margin-bottom:8px; font-size:13px;">
            Índice Multipeligro Climático (IMC)
        </div>

        <div style="font-size:12px; margin-bottom:8px;">
             <b>Muy Alto (0.75-1)</b>: Peligros climáticos extremos
            (inundaciones, sequías, calor/frío severo)
        </div>

        <div style="font-size:12px; margin-bottom:8px;">
             <b>Alto (0.5-0.75)</b>: Eventos climáticos intensos y frecuentes
            (lluvias intensas, olas de calor/frío)
        </div>

        <div style="font-size:12px; margin-bottom:8px;">
             <b>Medio (0.25-0.5)</b>: Variabilidad climática moderada
            (episodios de lluvia o temperatura fuera de lo normal)
        </div>

        <div style="font-size:12px;">
             <b>Bajo (0-0.25)</b>: Condiciones climáticas normales
            o poco significativas
        </div>
    </div>
    """
    map_obj.get_root().add_child(FloatLegend(html))


def add_geojson_layer(map_obj, geojson_data, style_function, popup_function, layer_name):
    fg = folium.FeatureGroup(name=layer_name, show=True)

    for feature in geojson_data.get("features", []):
        popup_html = popup_function(feature)

        folium.GeoJson(
            feature,
            style_function=style_function,
            highlight_function=lambda f: {
                "weight": 1.2,
                "color": "#222222",
                "fillOpacity": 0.95
            },
            popup=folium.Popup(popup_html, max_width=300)
        ).add_to(fg)

    fg.add_to(map_obj)


def add_simple_layer(map_obj, geojson_data, name):
    folium.GeoJson(
        geojson_data,
        name=name,
        style_function=layer_style_function
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

periodo = st.sidebar.selectbox(
    "Periodo",
    periodos,
    index=0
)

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

st.sidebar.subheader("Capas")
show_departamentos = st.sidebar.checkbox("Departamentos", value=False)
show_provincias = st.sidebar.checkbox("Provincias", value=False)
show_cuencas = st.sidebar.checkbox("Cuencas", value=False)

# =========================================================
# MAPA
# =========================================================
m = folium.Map(
    location=[-9, -75],
    zoom_start=5,
    tiles="OpenStreetMap",
    control_scale=True
)

# capa temática única
if usar_indice == "Sí":
    key = (tipo_indice, periodo)
    path = indice_index.get(key)

    if path and os.path.exists(path):
        data = load_geojson(path)
        add_geojson_layer(
            m,
            data,
            style_function=indice_style_function,
            popup_function=indice_popup_html,
            layer_name="Índice multipeligro"
        )
        add_indice_legend(m)
    else:
        st.warning("No existe archivo de IMC para la combinación seleccionada.")
else:
    key = (variable, estacion, periodo)
    path = climate_index.get(key)

    if path and os.path.exists(path):
        data = load_geojson(path)
        add_geojson_layer(
            m,
            data,
            style_function=climate_style_function(variable),
            popup_function=lambda feature: climate_popup_html(feature, variable),
            layer_name="Capa climática"
        )
        add_climate_legend(m, variable)
    else:
        st.warning("No existe archivo para la combinación seleccionada.")

# capas de referencia
if show_departamentos and os.path.exists(LAYER_PATHS["departamentos"]):
    deptos = load_geojson(LAYER_PATHS["departamentos"])
    add_simple_layer(m, deptos, "Departamentos")

if show_provincias and os.path.exists(LAYER_PATHS["provincias"]):
    provs = load_geojson(LAYER_PATHS["provincias"])
    add_simple_layer(m, provs, "Provincias")

if show_cuencas and os.path.exists(LAYER_PATHS["cuencas"]):
    cuencas = load_geojson(LAYER_PATHS["cuencas"])
    add_simple_layer(m, cuencas, "Cuencas")

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