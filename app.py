import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
import psycopg2
import pandas as pd
import calendar as cal_module
import os
import bcrypt
import json
import base64
from datetime import date, datetime, timedelta

# ---------------------------------------------------------
# Componente personalizado: la grilla interactiva
# ---------------------------------------------------------
_dir_componente = os.path.join(os.path.dirname(os.path.abspath(__file__)), "componente_agenda")
agenda_interactiva = components.declare_component("agenda_interactiva", path=_dir_componente)

# ---------------------------------------------------------
# ---------------------------------------------------------
# CONEXIÓN A LA BASE DE DATOS (Segura vía st.secrets)
# ---------------------------------------------------------
def get_connection():
    if hasattr(st, "secrets") and "postgres" in st.secrets:
        return psycopg2.connect(**st.secrets["postgres"])
    raise RuntimeError("No se encontró la configuración [postgres] en .streamlit/secrets.toml")

_ruta_logo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")

st.set_page_config(page_title="Turnero", layout="wide", page_icon=_ruta_logo)

# Inyectar estilos para compactar el calendario lateral y dar prioridad a la agenda
st.markdown("""
<style>
/* Calendario lateral ultra-compacto y estético */
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] button {
    min-height: 28px !important;
    height: 28px !important;
    padding: 0px !important;
    font-size: 11px !important;
    border-radius: 6px !important;
    margin-bottom: 0px !important;
}
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
    gap: 3px !important;
    margin-bottom: 2px !important;
}
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 1.5rem !important;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# LOGIN — nadie ve nada de la app sin iniciar sesión
# ---------------------------------------------------------
if "usuario" not in st.session_state:
    st.session_state["usuario"] = None

if st.session_state["usuario"] is None:
    col_a, col_b, col_c = st.columns([1, 1, 1])
    with col_b:
        st.image(_ruta_logo, width=90)
        st.markdown("## Ingresar")
        with st.form("form_login"):
            usuario_input = st.text_input("Usuario")
            password_input = st.text_input("Contraseña", type="password")
            entrar = st.form_submit_button("Ingresar", use_container_width=True)

        if entrar:
            conn_l = get_connection()
            res_login = pd.read_sql(
                """SELECT id, nombre_usuario, nombre_completo, password_hash, rol, profesional_id
                   FROM usuarios WHERE nombre_usuario = %s AND activo = true;""",
                conn_l, params=(usuario_input.strip(),),
            )
            conn_l.close()

            login_ok = False
            if not res_login.empty:
                hash_guardado = res_login.iloc[0]["password_hash"].encode("utf-8")
                if bcrypt.checkpw(password_input.encode("utf-8"), hash_guardado):
                    login_ok = True

            if login_ok:
                fila_u = res_login.iloc[0]
                st.session_state["usuario"] = {
                    "id": int(fila_u["id"]),
                    "nombre_usuario": fila_u["nombre_usuario"],
                    "nombre_completo": fila_u["nombre_completo"],
                    "rol": fila_u["rol"],
                    "profesional_id": int(fila_u["profesional_id"]) if fila_u["profesional_id"] is not None else None,
                }
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
    st.stop()

usuario_actual = st.session_state["usuario"]

st_autorefresh(interval=5000, key="auto_refresco")

col_logo, col_titulo, col_sesion = st.columns([0.8, 7, 2.2])
with col_logo:
    st.image(_ruta_logo, width=60)
with col_titulo:
    st.markdown("<h2 style='margin:0; padding-top:6px;'>Agenda de la clínica</h2>", unsafe_allow_html=True)
with col_sesion:
    st.markdown(
        f"<div style='text-align:right; color:#666; font-size:12px; margin-bottom:4px;'>"
        f"👤 <b>{usuario_actual['nombre_completo']}</b></div>",
        unsafe_allow_html=True,
    )
    if st.button("Cerrar sesión", use_container_width=True, key="btn_logout"):
        st.session_state["usuario"] = None
        st.rerun()

# ---------------------------------------------------------
# Barra lateral: Mini calendario optimizado
# ---------------------------------------------------------
MESES_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
            "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
DIAS_ES = ["L", "M", "M", "J", "V", "S", "D"]

if "fecha_seleccionada" not in st.session_state:
    st.session_state["fecha_seleccionada"] = date.today()
if "mes_visible" not in st.session_state:
    st.session_state["mes_visible"] = date.today().replace(day=1)

with st.sidebar:
    st.markdown("### 📅 Navegación")
    
    cq1, cq2, cq3 = st.columns(3)
    with cq1:
        if st.button("◀ Ayer", use_container_width=True):
            st.session_state["fecha_seleccionada"] -= timedelta(days=1)
            st.session_state["mes_visible"] = st.session_state["fecha_seleccionada"].replace(day=1)
            st.rerun()
    with cq2:
        if st.button("Hoy", use_container_width=True):
            st.session_state["fecha_seleccionada"] = date.today()
            st.session_state["mes_visible"] = date.today().replace(day=1)
            st.rerun()
    with cq3:
        if st.button("Mañana ▶", use_container_width=True):
            st.session_state["fecha_seleccionada"] += timedelta(days=1)
            st.session_state["mes_visible"] = st.session_state["fecha_seleccionada"].replace(day=1)
            st.rerun()

    mes_actual = st.session_state["mes_visible"]

    c_prev, c_label, c_next = st.columns([1, 4, 1])
    with c_prev:
        if st.button("◀", key="mes_prev", use_container_width=True):
            st.session_state["mes_visible"] = (mes_actual - timedelta(days=1)).replace(day=1)
            st.rerun()
    with c_label:
        st.markdown(
            f"<div style='text-align:center;font-weight:600;font-size:13px;padding-top:4px;'>"
            f"{MESES_ES[mes_actual.month]} {mes_actual.year}</div>",
            unsafe_allow_html=True,
        )
    with c_next:
        if st.button("▶", key="mes_next", use_container_width=True):
            ultimo_dia = cal_module.monthrange(mes_actual.year, mes_actual.month)[1]
            st.session_state["mes_visible"] = mes_actual.replace(day=ultimo_dia) + timedelta(days=1)
            st.rerun()

    cols_header = st.columns(7)
    for i, d in enumerate(DIAS_ES):
        cols_header[i].markdown(
            f"<div style='text-align:center;font-size:11px;color:#888;font-weight:600;'>{d}</div>",
            unsafe_allow_html=True,
        )

    cal_obj = cal_module.Calendar(firstweekday=0)
    for semana in cal_obj.monthdatescalendar(mes_actual.year, mes_actual.month):
        cols = st.columns(7)
        for i, dia in enumerate(semana):
            es_mes_actual = dia.month == mes_actual.month
            es_seleccionado = dia == st.session_state["fecha_seleccionada"]
            tipo_boton = "primary" if es_seleccionado else "secondary"
            etiqueta = str(dia.day) if es_mes_actual else " "
            if cols[i].button(etiqueta, key=f"dia_{dia.isoformat()}", type=tipo_boton, use_container_width=True):
                st.session_state["fecha_seleccionada"] = dia
                st.rerun()

    fecha = st.session_state["fecha_seleccionada"]
    st.divider()
    st.caption(f"🗓️ Fecha activa: **{fecha.strftime('%d/%m/%Y')}**")

dia_semana = fecha.isoweekday()

conn = get_connection()

# ---------------------------------------------------------
# Consultorios y Horarios
# ---------------------------------------------------------
consultorios_df = pd.read_sql("SELECT id, nombre FROM consultorios ORDER BY nombre;", conn)

if usuario_actual["rol"] == "profesional" and usuario_actual["profesional_id"] is not None:
    consultorios_propios = pd.read_sql(
        """SELECT DISTINCT consultorio_id FROM horarios_atencion
           WHERE profesional_id = %s AND dia_semana = %s;""",
        conn, params=(usuario_actual["profesional_id"], dia_semana),
    )
    ids_propios = consultorios_propios["consultorio_id"].tolist()
    consultorios_df = consultorios_df[consultorios_df["id"].isin(ids_propios)].reset_index(drop=True)

horarios_df = pd.read_sql(
    """
    SELECT h.consultorio_id, p.id AS profesional_id, p.nombre AS profesional,
           h.hora_desde, h.hora_hasta
    FROM horarios_atencion h
    JOIN profesionales p ON p.id = h.profesional_id
    WHERE h.dia_semana = %s;
    """,
    conn,
    params=(dia_semana,),
)

turnos_df = pd.read_sql(
    """
    SELECT t.id, t.consultorio_id, t.hora, t.paciente_id, t.profesional_id, t.estado,
           COALESCE(pac.apellido, '') AS apellido_paciente,
           COALESCE(pac.nombre, '(sin paciente)') AS paciente,
           pac.dni AS dni,
           pac.telefono AS telefono,
           COALESCE(os.nombre, 'Sin obra social') AS obra_social,
           COALESCE(s.nombre, '') AS servicio,
           p.nombre AS profesional,
           t.creado_en,
           uc.nombre_completo AS creado_por_nombre,
           um.nombre_completo AS modificado_por_nombre,
           t.modificado_en
    FROM turnos t
    JOIN profesionales p ON p.id = t.profesional_id
    LEFT JOIN pacientes pac ON pac.id = t.paciente_id
    LEFT JOIN obras_sociales os ON os.id = pac.obra_social_id
    LEFT JOIN servicios s ON s.id = t.servicio_id
    LEFT JOIN usuarios uc ON uc.id = t.creado_por
    LEFT JOIN usuarios um ON um.id = t.modificado_por
    WHERE t.fecha = %s;
    """,
    conn,
    params=(fecha,),
)

ids_pacientes_hoy = [int(x) for x in turnos_df["paciente_id"].dropna().unique().tolist()]
historial_por_paciente = {}
if ids_pacientes_hoy:
    historial_df = pd.read_sql(
        """
        SELECT * FROM (
            SELECT t.paciente_id, t.fecha, t.hora, t.estado,
                   p.nombre AS profesional,
                   COALESCE(s.nombre, 'Consulta') AS servicio,
                   ROW_NUMBER() OVER (PARTITION BY t.paciente_id ORDER BY t.fecha DESC, t.hora DESC) AS rn
            FROM turnos t
            JOIN profesionales p ON p.id = t.profesional_id
            LEFT JOIN servicios s ON s.id = t.servicio_id
            WHERE t.paciente_id = ANY(%s) AND t.fecha < %s
        ) sub
        WHERE rn <= 5
        ORDER BY paciente_id, fecha DESC, hora DESC;
        """,
        conn,
        params=(ids_pacientes_hoy, fecha),
    )
    for pid, grupo in historial_df.groupby("paciente_id"):
        historial_por_paciente[int(pid)] = [
            {
                "fecha": row["fecha"].strftime("%d/%m/%Y"),
                "hora": row["hora"].strftime("%H:%M") if hasattr(row["hora"], "strftime") else str(row["hora"])[:5],
                "profesional": row["profesional"],
                "servicio": row["servicio"],
                "estado": row["estado"],
            }
            for _, row in grupo.iterrows()
        ]

conn.close()

if horarios_df.empty:
    st.info("Ningún profesional tiene horario cargado para este día de la semana.")
    st.stop()

ESTADOS = [
    "pendiente",
    "confirmado",
    "en sala de espera",
    "esta siendo atendido",
    "finalizo",
    "ausente",
    "cancelado por paciente",
    "cancelado por profesional",
]
def clase_estado(estado):
    return "estado-" + estado.replace(" ", "-")

hora_inicio = horarios_df["hora_desde"].min()
hora_fin = horarios_df["hora_hasta"].max()

base = datetime.combine(fecha, datetime.min.time())
def a_datetime(t):
    if isinstance(t, timedelta):
        return base + t
    return datetime.combine(fecha, t)

actual = a_datetime(hora_inicio)
fin = a_datetime(hora_fin)

filas_horas = []
while actual < fin:
    filas_horas.append(actual.time())
    actual += timedelta(minutes=5)

encabezados = {}
for _, cons in consultorios_df.iterrows():
    cons_id, cons_nombre = cons["id"], cons["nombre"]
    profesionales_dia = horarios_df[horarios_df["consultorio_id"] == cons_id]["profesional"].unique()
    if len(profesionales_dia) == 0:
        encabezados[cons_nombre] = f"{cons_nombre}\n(sin atención)"
    else:
        encabezados[cons_nombre] = f"{cons_nombre}\n{' / '.join(profesionales_dia)}"

ALTO_FILA = 24
ALTO_ENCABEZADO = 54

columnas = [encabezados[n] for n in consultorios_df["nombre"]]
tabla = pd.DataFrame(index=[h.strftime("%H:%M") for h in filas_horas], columns=columnas)
estado_tabla = pd.DataFrame(index=[h.strftime("%H:%M") for h in filas_horas], columns=columnas)
tooltip_tabla = pd.DataFrame(index=[h.strftime("%H:%M") for h in filas_horas], columns=columnas)
id_tabla = pd.DataFrame(index=[h.strftime("%H:%M") for h in filas_horas], columns=columnas)
detalle_tabla = pd.DataFrame(index=[h.strftime("%H:%M") for h in filas_horas], columns=columnas)

for _, cons in consultorios_df.iterrows():
    cons_id, cons_nombre = cons["id"], cons["nombre"]
    col = encabezados[cons_nombre]
    turnos_cons = turnos_df[turnos_df["consultorio_id"] == cons_id]

    for h in filas_horas:
        etiqueta = h.strftime("%H:%M")
        turno = turnos_cons[turnos_cons["hora"] == h]
        if not turno.empty:
            t = turno.iloc[0]
            tel = t["telefono"] if t["telefono"] else "sin tel."
            servicio = t["servicio"] if t["servicio"] else "Consulta"
            tooltip = f'Tel: {tel} · {t["obra_social"]}'
            if t["modificado_por_nombre"] and pd.notna(t["modificado_en"]):
                tooltip += f' · Modificado por {t["modificado_por_nombre"]} el {t["modificado_en"].strftime("%d/%m %H:%M")}'
            elif t["creado_por_nombre"]:
                tooltip += f' · Cargado por {t["creado_por_nombre"]}'
            nombre_completo = f'{t["apellido_paciente"]}, {t["paciente"]}'.strip(", ").upper()
            label_html = (
                f'<div class="nombre-paciente">{nombre_completo}</div>'
                f'<div class="detalle-turno">{t["profesional"]}: {servicio}</div>'
            )
            tabla.loc[etiqueta, col] = label_html
            estado_tabla.loc[etiqueta, col] = t["estado"]
            tooltip_tabla.loc[etiqueta, col] = tooltip
            id_tabla.loc[etiqueta, col] = int(t["id"])

            detalle = {
                "nombre": nombre_completo,
                "dni": t["dni"] if pd.notna(t["dni"]) and t["dni"] else "—",
                "telefono": tel,
                "obra_social": t["obra_social"],
                "profesional": t["profesional"],
                "servicio": servicio,
                "consultorio": cons_nombre,
                "hora": etiqueta,
                "estado": t["estado"],
                "creado_por": t["creado_por_nombre"] or "—",
                "creado_en": t["creado_en"].strftime("%d/%m/%Y %H:%M") if pd.notna(t["creado_en"]) else "—",
                "modificado_por": t["modificado_por_nombre"] or "—",
                "modificado_en": t["modificado_en"].strftime("%d/%m/%Y %H:%M") if pd.notna(t["modificado_en"]) else "—",
                "historial": historial_por_paciente.get(int(t["paciente_id"]), []) if pd.notna(t["paciente_id"]) else [],
            }
            detalle_json = json.dumps(detalle, ensure_ascii=False)
            detalle_tabla.loc[etiqueta, col] = base64.b64encode(detalle_json.encode("utf-8")).decode("ascii")
        else:
            tabla.loc[etiqueta, col] = ""
            estado_tabla.loc[etiqueta, col] = ""
            tooltip_tabla.loc[etiqueta, col] = ""
            id_tabla.loc[etiqueta, col] = None
            detalle_tabla.loc[etiqueta, col] = ""

# Armar HTML de la grilla
horas_index = list(tabla.index)
skip = {col: 0 for col in columnas}
filas_html = []

for i, hora_label in enumerate(horas_index):
    fila = f'<tr><td class="hora-cell">{hora_label}</td>'
    for _, cons in consultorios_df.iterrows():
        cons_id, cons_nombre = cons["id"], cons["nombre"]
        col = encabezados[cons_nombre]
        if skip[col] > 0:
            skip[col] -= 1
            continue
        val = tabla.loc[hora_label, col]
        if val == "":
            fila += (
                f'<td class="libre" data-hora="{hora_label}" data-cons-id="{cons_id}" data-cons-nombre="{cons_nombre}" '
                f'title="Click para nuevo turno ({hora_label} - {cons_nombre})">'
                f'<span class="slot-libre-plus">+</span>'
                f'</td>'
            )
        else:
            estado_val = estado_tabla.loc[hora_label, col]
            tooltip_val = tooltip_tabla.loc[hora_label, col]
            span = 1
            j = i + 1
            while j < len(horas_index) and tabla.loc[horas_index[j], col] == val:
                span += 1
                j += 1
            skip[col] = span - 1
            ids_bloque = [
                str(id_tabla.loc[horas_index[k], col])
                for k in range(i, i + span)
                if id_tabla.loc[horas_index[k], col] is not None
            ]
            detalle_val = detalle_tabla.loc[hora_label, col]
            fila += (
                f'<td class="celda-turno" rowspan="{span}" title="{tooltip_val}">'
                f'<div class="tarjeta-turno {clase_estado(estado_val)}" '
                f'data-ids="{",".join(ids_bloque)}" data-estado="{estado_val}">'
                f'<div class="barra-estado"></div>'
                f'<div class="contenido-turno" data-detalle="{detalle_val}">{val}</div>'
                f'</div>'
                f'</td>'
            )
    fila += "</tr>"
    filas_html.append(fila)

encabezados_html = "".join(f'<th>{c.replace(chr(10), "<br>")}</th>' for c in columnas)

es_hoy = fecha == date.today()
linea_ahora_html = '<div class="ahora-linea" id="ahora-linea" style="display:none;"><span class="ahora-etiqueta" id="ahora-etiqueta"></span></div>' if es_hoy else ""
hora_inicio_grilla = filas_horas[0] if filas_horas else None
total_franjas = len(filas_horas)

script_linea = ""
if es_hoy and hora_inicio_grilla:
    script_linea = f"""
    <script>
    function actualizarLineaAhora() {{
        const ahora = new Date();
        const inicioGrilla = new Date(ahora);
        inicioGrilla.setHours({hora_inicio_grilla.hour}, {hora_inicio_grilla.minute}, 0, 0);
        const minutosDesdeInicio = (ahora - inicioGrilla) / 60000;
        const franjaFraccion = minutosDesdeInicio / 5;
        const linea = document.getElementById('ahora-linea');
        const etiqueta = document.getElementById('ahora-etiqueta');
        if (!linea) return;
        if (minutosDesdeInicio < 0 || franjaFraccion > {total_franjas}) {{
            linea.style.display = 'none';
            return;
        }}
        const offset = {ALTO_ENCABEZADO} + franjaFraccion * {ALTO_FILA};
        linea.style.display = 'block';
        linea.style.top = offset + 'px';
        const hh = String(ahora.getHours()).padStart(2, '0');
        const mm = String(ahora.getMinutes()).padStart(2, '0');
        etiqueta.textContent = hh + ':' + mm;
    }}
    actualizarLineaAhora();
    setInterval(actualizarLineaAhora, 1000);
    </script>
    """

tabla_html = f"""
<style>
body {{ margin: 0; font-family: -apple-system, "Segoe UI", sans-serif; }}
.agenda-wrap {{
    position: relative;
    max-height: 650px;
    overflow-y: auto;
    border: 1px solid #e2e4e9;
    border-radius: 12px;
    background: #ffffff;
    box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}}
.agenda-tabla {{ border-collapse: separate; border-spacing: 0; width: 100%; font-size: 13px; table-layout: fixed; }}
.agenda-tabla th {{
    position: sticky; top: 0; background: #fafafc; z-index: 2;
    padding: 8px; border-bottom: 2px solid #e5e7eb; text-align: left; font-size: 12px;
    color: #374151; font-weight: 700;
    height: {ALTO_ENCABEZADO}px; box-sizing: border-box;
}}
.agenda-tabla td {{
    border: none; padding: 0; vertical-align: top;
    height: {ALTO_FILA}px; box-sizing: border-box;
    border-right: 1px solid #f0f2f5;
}}
.agenda-tabla td:last-child {{ border-right: none; }}
.hora-cell {{
    color: #9ca3af; font-size: 10.5px; white-space: nowrap; width: 52px;
    padding-top: 3px !important; text-align: right; padding-right: 8px !important;
    background: #fbfbfc; border-right: 1px solid #e5e7eb !important; font-weight: 500;
}}
.hora-header {{ width: 52px; background: #fbfbfc !important; border-right: 1px solid #e5e7eb !important; }}
.celda-turno {{ padding: 1.5px 3px !important; }}
.tarjeta-turno {{
    height: 100%; box-sizing: border-box;
    display: flex; align-items: stretch;
    overflow: hidden;
    border-radius: 8px;
    background: #f4f4f6;
    box-shadow: 0 1px 2px rgba(20,20,30,0.04);
    cursor: pointer;
}}
.barra-estado {{
    width: 6px; flex-shrink: 0; background: #ccc;
    border-radius: 8px 0 0 8px;
    cursor: pointer;
    transition: width 0.15s ease;
}}
.barra-estado:hover {{ width: 12px; }}
.contenido-turno {{
    flex: 1;
    padding: 4px 8px; overflow: hidden; min-width: 0;
    cursor: pointer;
}}
.nombre-paciente {{
    font-weight: 700; text-transform: uppercase; font-size: 12px;
    color: #1f2937; line-height: 1.25;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.detalle-turno {{
    font-weight: 400; font-size: 10.5px; color: #6b7280;
    line-height: 1.3; margin-top: 1px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.estado-pendiente                 .barra-estado {{ background: #9ca3af; }}
.estado-confirmado                .barra-estado {{ background: #10b981; }}
.estado-en-sala-de-espera         .barra-estado {{ background: #3b82f6; }}
.estado-esta-siendo-atendido      .barra-estado {{ background: #8b5cf6; }}
.estado-finalizo                  .barra-estado {{ background: #4b5563; }}
.estado-ausente                   .barra-estado {{ background: #ef4444; }}
.estado-cancelado-por-paciente    .barra-estado {{ background: #dc2626; }}
.estado-cancelado-por-profesional .barra-estado {{ background: #dc2626; }}
.estado-pendiente                 {{ background-color: #f3f4f6; }}
.estado-confirmado                {{ background-color: #ecfdf5; }}
.estado-en-sala-de-espera         {{ background-color: #eff6ff; }}
.estado-esta-siendo-atendido      {{ background-color: #f5f3ff; }}
.estado-finalizo                  {{ background-color: #e5e7eb; }}
.estado-ausente                   {{ background-color: #fef2f2; }}
.estado-cancelado-por-paciente    {{ background-color: #fee2e2; }}
.estado-cancelado-por-profesional {{ background-color: #fee2e2; }}
.estado-cancelado-por-paciente .nombre-paciente,
.estado-cancelado-por-profesional .nombre-paciente {{
    text-decoration: line-through; color: #9ca3af;
}}
.libre {{
    background: transparent;
    cursor: pointer;
    position: relative;
    transition: background 0.12s ease;
    border-bottom: 1px dashed #f3f4f6;
}}
.libre:hover {{
    background: #eef2ff !important;
}}
.slot-libre-plus {{
    display: none;
    position: absolute;
    right: 8px;
    top: 2px;
    font-size: 13px;
    font-weight: 700;
    color: #4f46e5;
}}
.libre:hover .slot-libre-plus {{
    display: block;
}}
.ahora-linea {{
    position: absolute; left: 0; right: 0; height: 2px; background: #2563eb;
    z-index: 3; pointer-events: none; border-radius: 2px;
}}
.ahora-etiqueta {{
    position: absolute; left: 4px; top: -8px; background: #2563eb; color: #fff;
    font-size: 9.5px; padding: 1px 6px; border-radius: 8px; font-weight: 600;
}}
</style>
<div class="agenda-wrap">
{linea_ahora_html}
<table class="agenda-tabla">
<thead><tr><th class="hora-header"></th>{encabezados_html}</tr></thead>
<tbody>
{''.join(filas_html)}
</tbody>
</table>
</div>
{script_linea}
"""

ICONO_ESTADO = {
    "pendiente": "⚪", "confirmado": "🟢", "en sala de espera": "🔵", "esta siendo atendido": "🟣",
    "finalizo": "⚫", "ausente": "🔴", "cancelado por paciente": "❌", "cancelado por profesional": "🚫",
}

# ---------------------------------------------------------
# FUNCIÓN: Formulario para crear un nuevo turno (usado en el modal)
# ---------------------------------------------------------
def modal_contenido_nuevo_turno(cons_id_inicial=None, hora_inicial_str=None):
    st.markdown("### ➕ Cargar nuevo turno")
    
    nombres_consultorios = consultorios_df["nombre"].tolist()
    idx_cons = 0
    if cons_id_inicial is not None:
        matched = consultorios_df.index[consultorios_df["id"] == cons_id_inicial].tolist()
        if matched:
            idx_cons = matched[0]
            
    col1, col2 = st.columns(2)
    with col1:
        consultorio_sel = st.selectbox("Consultorio", options=nombres_consultorios, index=idx_cons)
    
    cons_id_sel = int(consultorios_df.loc[consultorios_df["nombre"] == consultorio_sel, "id"].iloc[0])
    horarios_cons = horarios_df[horarios_df["consultorio_id"] == cons_id_sel]
    turnos_cons_sel = turnos_df[turnos_df["consultorio_id"] == cons_id_sel]
    ocupadas = set(turnos_cons_sel["hora"])

    profesionales_cons = horarios_cons[["profesional_id", "profesional"]].drop_duplicates()
    if profesionales_cons.empty:
        st.warning("Este consultorio no tiene ningún profesional atendiendo hoy.")
        return

    with col2:
        if len(profesionales_cons) == 1:
            profesional_sel_nombre = profesionales_cons.iloc[0]["profesional"]
            profesional_id_sel = int(profesionales_cons.iloc[0]["profesional_id"])
            st.text_input("Profesional", value=profesional_sel_nombre, disabled=True)
        else:
            profesional_sel_nombre = st.selectbox("Profesional", options=profesionales_cons["profesional"])
            profesional_id_sel = int(
                profesionales_cons.loc[profesionales_cons["profesional"] == profesional_sel_nombre, "profesional_id"].iloc[0]
            )

    horarios_cons_sel = horarios_cons[horarios_cons["profesional_id"] == profesional_id_sel]

    conn_sv = get_connection()
    servicios_df = pd.read_sql(
        "SELECT id, nombre, duracion_minutos FROM servicios WHERE profesional_id = %s ORDER BY nombre;",
        conn_sv, params=(profesional_id_sel,),
    )
    conn_sv.close()

    if servicios_df.empty:
        st.warning(f"{profesional_sel_nombre} todavía no tiene servicios cargados. Agregalo en ⚙️ Servicios.")
        return

    col3, col4 = st.columns(2)
    with col3:
        servicio_opciones = [f"{r['nombre']} ({r['duracion_minutos']} min)" for _, r in servicios_df.iterrows()]
        servicio_sel_str = st.selectbox("Servicio", options=servicio_opciones)
        servicio_row = servicios_df.iloc[servicio_opciones.index(servicio_sel_str)]
        servicio_id_sel = int(servicio_row["id"])
        duracion_min = int(servicio_row["duracion_minutos"])

    slots_necesarios = max(1, -(-duracion_min // 5))

    def hay_lugar(h_inicio):
        dt = a_datetime(h_inicio)
        for i in range(slots_necesarios):
            h = (dt + timedelta(minutes=5 * i)).time()
            activo = horarios_cons_sel[
                (horarios_cons_sel["hora_desde"] <= h) & (h < horarios_cons_sel["hora_hasta"])
            ]
            if activo.empty or h in ocupadas:
                return False
        return True

    franjas_libres = [h for h in filas_horas if hay_lugar(h)]
    opciones_horas = [h.strftime("%H:%M") for h in franjas_libres]

    idx_hora = 0
    if hora_inicial_str and hora_inicial_str in opciones_horas:
        idx_hora = opciones_horas.index(hora_inicial_str)

    with col4:
        if franjas_libres:
            hora_sel_str = st.selectbox("Horario", options=opciones_horas, index=idx_hora)
            hora_sel = datetime.strptime(hora_sel_str, "%H:%M").time()
        else:
            hora_sel = None
            st.warning("No hay huecos disponibles para esta duración.")

    st.markdown("---")
    dni_input = st.text_input("DNI del paciente")

    paciente_id_existente = None
    apellido_nuevo = nombre_nuevo = telefono_nuevo = ""
    obra_social_id_nueva = None

    if dni_input:
        conn_b = get_connection()
        res = pd.read_sql("SELECT id, apellido, nombre, telefono FROM pacientes WHERE dni = %s;", conn_b, params=(dni_input,))
        conn_b.close()
        if not res.empty:
            paciente_id_existente = int(res.iloc[0]["id"])
            st.success(f"Paciente: **{res.iloc[0]['nombre']} {res.iloc[0]['apellido']}** (Tel: {res.iloc[0]['telefono']})")
        else:
            st.info("Paciente nuevo. Completa sus datos:")
            c1, c2, c3 = st.columns(3)
            with c1:
                apellido_nuevo = st.text_input("Apellido")
            with c2:
                nombre_nuevo = st.text_input("Nombre")
            with c3:
                telefono_nuevo = st.text_input("Teléfono")

            conn_os = get_connection()
            obras_sociales_df = pd.read_sql("SELECT id, nombre FROM obras_sociales ORDER BY nombre;", conn_os)
            conn_os.close()

            c4, c5 = st.columns([2, 1])
            with c4:
                opciones_os = ["— Elegir —"] + obras_sociales_df["nombre"].tolist() + ["➕ Agregar nueva..."]
                os_sel = st.selectbox("Obra social", options=opciones_os)
            with c5:
                if os_sel == "➕ Agregar nueva...":
                    os_nueva_nombre = st.text_input("Nueva obra social")
                    if os_nueva_nombre.strip():
                        conn_os2 = get_connection()
                        cur_os = conn_os2.cursor()
                        cur_os.execute(
                            "INSERT INTO obras_sociales (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING RETURNING id;",
                            (os_nueva_nombre.strip(),),
                        )
                        fila_os = cur_os.fetchone()
                        if fila_os is None:
                            cur_os.execute("SELECT id FROM obras_sociales WHERE nombre = %s;", (os_nueva_nombre.strip(),))
                            fila_os = cur_os.fetchone()
                        conn_os2.commit()
                        obra_social_id_nueva = int(fila_os[0])
                        cur_os.close()
                        conn_os2.close()
                elif os_sel != "— Elegir —":
                    obra_social_id_nueva = int(obras_sociales_df.loc[obras_sociales_df["nombre"] == os_sel, "id"].iloc[0])

    puede_guardar = dni_input and hora_sel is not None and (
        paciente_id_existente is not None or (apellido_nuevo and nombre_nuevo)
    )

    c_btn1, c_btn2 = st.columns([3, 1])
    with c_btn1:
        if st.button("💾 Guardar turno", type="primary", disabled=not puede_guardar, use_container_width=True):
            dt_inicio = a_datetime(hora_sel)
            horas_a_reservar = [(dt_inicio + timedelta(minutes=5 * i)).time() for i in range(slots_necesarios)]

            conn_w = get_connection()
            cur = conn_w.cursor()
            try:
                if paciente_id_existente is not None:
                    paciente_id = paciente_id_existente
                else:
                    cur.execute(
                        "INSERT INTO pacientes (apellido, nombre, dni, telefono, obra_social_id) VALUES (%s,%s,%s,%s,%s) RETURNING id;",
                        (apellido_nuevo, nombre_nuevo, dni_input, telefono_nuevo, obra_social_id_nueva),
                    )
                    paciente_id = cur.fetchone()[0]

                for h in horas_a_reservar:
                    cur.execute(
                        """INSERT INTO turnos (fecha, hora, profesional_id, consultorio_id, paciente_id,
                                                servicio_id, estado, creado_por)
                           VALUES (%s,%s,%s,%s,%s,%s,'pendiente',%s);""",
                        (fecha, h, profesional_id_sel, cons_id_sel, paciente_id, servicio_id_sel, usuario_actual["id"]),
                    )
                conn_w.commit()
                st.session_state["mostrar_modal_turno"] = False
                st.rerun()
            except psycopg2.errors.UniqueViolation:
                conn_w.rollback()
                st.error("Ese horario ya fue ocupado.")
            finally:
                cur.close()
                conn_w.close()
    with c_btn2:
        if st.button("Cancelar", use_container_width=True):
            st.session_state["mostrar_modal_turno"] = False
            st.rerun()

# Definición del modal según soporte de Streamlit
if hasattr(st, "dialog"):
    @st.dialog("Cargar Turno", width="large")
    def abrir_dialogo_turno(cons_id=None, hora=None):
        modal_contenido_nuevo_turno(cons_id, hora)
else:
    def abrir_dialogo_turno(cons_id=None, hora=None):
        st.session_state["mostrar_modal_turno"] = True

# ---------------------------------------------------------
# PESTAÑAS PRINCIPALES
# ---------------------------------------------------------
tab_agenda, tab_servicios, tab_pacientes = st.tabs(
    ["📅 Agenda", "⚙️ Servicios", "👥 Pacientes"]
)

with tab_agenda:
    c_tit, c_btn = st.columns([8, 2])
    with c_tit:
        st.markdown(
            f"<h3 style='margin:0; padding-bottom:8px;'>Agenda del {fecha.strftime('%d/%m/%Y')}</h3>",
            unsafe_allow_html=True
        )
    with c_btn:
        if st.button("➕ Nuevo Turno", type="primary", use_container_width=True):
            if hasattr(st, "dialog"):
                abrir_dialogo_turno()
            else:
                st.session_state["mostrar_modal_turno"] = True

    # Renderizar la grilla interactiva
    resultado_click = agenda_interactiva(
        html=tabla_html,
        estados=ESTADOS,
        iconos=ICONO_ESTADO,
        es_hoy=es_hoy,
        hora_inicio_h=hora_inicio_grilla.hour if hora_inicio_grilla else 0,
        hora_inicio_m=hora_inicio_grilla.minute if hora_inicio_grilla else 0,
        alto_fila=ALTO_FILA,
        alto_encabezado=ALTO_ENCABEZADO,
        total_franjas=total_franjas,
        key="agenda_click",
    )

    # Manejo de clics (estados, borrado o click en celda libre)
    if resultado_click and resultado_click.get("ts") != st.session_state.get("_ultimo_click_ts"):
        st.session_state["_ultimo_click_ts"] = resultado_click["ts"]
        
        tipo_accion = resultado_click.get("tipo")
        
        # 1. Click en celda libre -> Abrir modal con hora y consultorio
        if tipo_accion == "nuevo_turno":
            h_click = resultado_click.get("hora")
            c_click = resultado_click.get("consultorio_id")
            st.session_state["modal_cons_id"] = c_click
            st.session_state["modal_hora"] = h_click
            st.session_state["mostrar_modal_turno"] = True
            st.rerun()

        # 2. Eliminación
        elif resultado_click.get("estado") == "__eliminar__":
            ids_cambiar = resultado_click.get("ids", [])
            if ids_cambiar:
                conn_d = get_connection()
                cur_d = conn_d.cursor()
                cur_d.execute("DELETE FROM turnos WHERE id = ANY(%s);", (ids_cambiar,))
                conn_d.commit()
                cur_d.close()
                conn_d.close()
                st.rerun()

        # 3. Cambio de estado
        elif resultado_click.get("estado"):
            ids_cambiar = resultado_click.get("ids", [])
            nuevo_estado_click = resultado_click.get("estado")
            if ids_cambiar and nuevo_estado_click:
                conn_u = get_connection()
                cur_u = conn_u.cursor()
                cur_u.execute(
                    """UPDATE turnos SET estado = %s, modificado_por = %s, modificado_en = now()
                       WHERE id = ANY(%s);""",
                    (nuevo_estado_click, usuario_actual["id"], ids_cambiar),
                )
                conn_u.commit()
                cur_u.close()
                conn_u.close()
                st.rerun()

    # Si se activó la apertura del modal
    if st.session_state.get("mostrar_modal_turno"):
        if hasattr(st, "dialog"):
            abrir_dialogo_turno(
                cons_id=st.session_state.get("modal_cons_id"),
                hora=st.session_state.get("modal_hora")
            )
        else:
            with st.expander("➕ Cargar nuevo turno", expanded=True):
                modal_contenido_nuevo_turno(
                    cons_id_inicial=st.session_state.get("modal_cons_id"),
                    hora_inicial_str=st.session_state.get("modal_hora")
                )

    st.caption("⚡ Haz click en un casillero vacío para agregar un turno, o en la barra de color para cambiar su estado.")

with tab_servicios:
    st.subheader("Administrar servicios")
    conn_s = get_connection()
    servicios_actuales = pd.read_sql(
        """SELECT s.id, p.nombre AS profesional, s.nombre AS servicio, s.duracion_minutos
           FROM servicios s
           JOIN profesionales p ON p.id = s.profesional_id
           ORDER BY p.nombre, s.nombre;""",
        conn_s,
    )
    todos_profesionales = pd.read_sql("SELECT id, nombre FROM profesionales ORDER BY nombre;", conn_s)
    conn_s.close()

    if servicios_actuales.empty:
        st.caption("Todavía no cargaste ningún servicio.")
    else:
        st.dataframe(
            servicios_actuales[["profesional", "servicio", "duracion_minutos"]],
            hide_index=True, use_container_width=True,
        )

    c0, c1, c2, c3 = st.columns([2, 3, 2, 2])
    with c0:
        prof_nuevo_serv = st.selectbox("Profesional", options=todos_profesionales["nombre"], key="prof_nuevo_serv")
    with c1:
        nuevo_serv_nombre = st.text_input("Nombre del servicio", key="nuevo_serv_nombre")
    with c2:
        nuevo_serv_duracion = st.number_input(
            "Duración (min, múltiplo de 5)", min_value=5, step=5, value=30, key="nuevo_serv_dur"
        )
    with c3:
        st.write("")
        st.write("")
        if st.button("Agregar servicio"):
            if nuevo_serv_nombre.strip():
                prof_id_nuevo_serv = int(
                    todos_profesionales.loc[todos_profesionales["nombre"] == prof_nuevo_serv, "id"].iloc[0]
                )
                conn_s2 = get_connection()
                cur_s = conn_s2.cursor()
                cur_s.execute(
                    "INSERT INTO servicios (nombre, duracion_minutos, profesional_id) VALUES (%s,%s,%s);",
                    (nuevo_serv_nombre.strip(), int(nuevo_serv_duracion), prof_id_nuevo_serv),
                )
                conn_s2.commit()
                cur_s.close()
                conn_s2.close()
                st.success("Servicio agregado.")
                st.rerun()
            else:
                st.warning("Escribí un nombre para el servicio.")

with tab_pacientes:
    st.subheader("Pacientes")
    st.info("Todavía no armamos esta sección — la vamos a construir con la referencia que me pases de cómo la querés.")
    conn_p = get_connection()
    total_pac = pd.read_sql("SELECT count(*) AS total FROM pacientes;", conn_p).iloc[0]["total"]
    conn_p.close()
    st.caption(f"Por ahora, hay {total_pac} pacientes cargados en la base.")
