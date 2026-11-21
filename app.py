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
/* Eliminar el parpadeo blanco/atenuado de Streamlit durante la recarga en segundo plano */
[data-testid="stAppViewContainer"],
[data-testid="stMainBlockContainer"],
.element-container {
    opacity: 1 !important;
    filter: none !important;
    transition: none !important;
}
.stCustomComponentV1,
.stCustomComponentV1 iframe {
    opacity: 1 !important;
    filter: none !important;
    transition: none !important;
    min-height: 730px !important;
    height: 730px !important;
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

if not st.session_state.get("mostrar_modal_turno"):
    st_autorefresh(interval=25000, key="auto_refresco")  # Sincronización en vivo cada 25s (sin saturar la red)

col_logo, col_titulo, col_sesion = st.columns([0.8, 6.2, 3])
with col_logo:
    st.image(_ruta_logo, width=60)
with col_titulo:
    st.markdown("<h2 style='margin:0; padding-top:6px;'>Agenda de la clínica</h2>", unsafe_allow_html=True)
with col_sesion:
    c_user, c_ref = st.columns([2, 1])
    with c_user:
        st.markdown(
            f"<div style='text-align:right; color:#666; font-size:12px; padding-top:4px;'>"
            f"👤 <b>{usuario_actual['nombre_completo']}</b></div>",
            unsafe_allow_html=True,
        )
    with c_ref:
        if st.button("🔄", help="Actualizar agenda ahora", use_container_width=True, key="btn_refresco"):
            st.rerun()
    if st.button("Cerrar sesión", use_container_width=True, key="btn_logout"):
        st.session_state["usuario"] = None
        st.rerun()

# ---------------------------------------------------------
# Funciones de consulta cacheadas para velocidad máxima
# ---------------------------------------------------------
@st.cache_data(ttl=60)
def cargar_consultorios_base():
    c = get_connection()
    df = pd.read_sql("SELECT id, nombre FROM consultorios ORDER BY nombre;", c)
    c.close()
    return df

@st.cache_data(ttl=60)
def cargar_horarios_dia(dia):
    c = get_connection()
    df = pd.read_sql(
        """
        SELECT h.consultorio_id, p.id AS profesional_id, p.nombre AS profesional,
               h.hora_desde, h.hora_hasta
        FROM horarios_atencion h
        JOIN profesionales p ON p.id = h.profesional_id
        WHERE h.dia_semana = %s;
        """,
        c, params=(dia,),
    )
    c.close()
    return df

consultorios_df = cargar_consultorios_base().copy()

# ---------------------------------------------------------
# Barra lateral: Mini calendario optimizado y Tachar agenda
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

    # ---------------------------------------------------------
    # SECCIÓN: TACHAR AGENDA (Bloqueos de consultorios)
    # ---------------------------------------------------------
    st.markdown("---")
    with st.expander("🚫 Tachar agenda", expanded=False):
        st.markdown("<div style='font-size:12px;color:#64748b;margin-bottom:8px;'>Bloquear un consultorio por ausencia, mantenimiento o feriado.</div>", unsafe_allow_html=True)
        
        nombres_cons_lista = consultorios_df["nombre"].tolist()
        cons_bloq_sel = st.selectbox("Consultorio a tachar", options=nombres_cons_lista, key="sel_cons_bloq")
        id_cons_bloq = int(consultorios_df.loc[consultorios_df["nombre"] == cons_bloq_sel, "id"].iloc[0])
        
        fecha_bloq = st.date_input("Fecha a tachar", value=fecha, key="fecha_bloq_input")
        
        # Horas de inicio y fin (cada 5 min de 07:00 a 20:30)
        opciones_horas_bloq = [f"{h:02d}:{m:02d}" for h in range(7, 21) for m in (0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55)]
        c_h1, c_h2 = st.columns(2)
        with c_h1:
            idx_d = opciones_horas_bloq.index("08:00") if "08:00" in opciones_horas_bloq else 0
            h_desde_str = st.selectbox("Hora inicio", options=opciones_horas_bloq, index=idx_d, key="h_desde_bloq")
        with c_h2:
            idx_h = opciones_horas_bloq.index("12:00") if "12:00" in opciones_horas_bloq else 10
            h_hasta_str = st.selectbox("Hora fin", options=opciones_horas_bloq, index=idx_h, key="h_hasta_bloq")
            
        motivo_bloq = st.text_input("Motivo del bloqueo *", placeholder="Ej: Profesional ausente, Mantenimiento", key="txt_motivo_bloq").strip()
        
        t_desde = datetime.strptime(h_desde_str, "%H:%M").time()
        t_hasta = datetime.strptime(h_hasta_str, "%H:%M").time()
        
        horas_validas = t_hasta > t_desde
        if not horas_validas:
            st.caption("⚠️ La hora de fin debe ser posterior a la de inicio.")
        elif not motivo_bloq:
            st.caption("⚠️ Debe ingresar un motivo o comentario.")
            
        # Advertencia de turnos preexistentes en ese consultorio y horario
        turnos_conflicto = []
        if horas_validas and id_cons_bloq:
            conn_chk = get_connection()
            tc_df = pd.read_sql(
                """SELECT t.hora, pac.nombre, pac.apellido, p.nombre AS profesional
                   FROM turnos t
                   LEFT JOIN pacientes pac ON pac.id = t.paciente_id
                   JOIN profesionales p ON p.id = t.profesional_id
                   WHERE t.consultorio_id = %s AND t.fecha = %s AND t.hora >= %s AND t.hora < %s
                   ORDER BY t.hora;""",
                conn_chk,
                params=(id_cons_bloq, fecha_bloq, t_desde, t_hasta)
            )
            conn_chk.close()
            turnos_conflicto = tc_df.to_dict("records")
            
        confirmar_con_turnos = True
        if turnos_conflicto:
            st.warning(f"⚠️ Atención: Hay {len(turnos_conflicto)} turno(s) en esa franja:")
            for tc in turnos_conflicto:
                nom_p = f"{tc['apellido'] or ''}, {tc['nombre'] or ''}".strip(', ')
                st.caption(f"• **{tc['hora'].strftime('%H:%M')}** — {nom_p} ({tc['profesional']})")
            confirmar_con_turnos = st.checkbox("☑️ Deseo tachar igualmente (los turnos existentes se conservarán)", key="chk_confirma_bloq_turnos")
            
        puede_guardar_bloq = horas_validas and bool(motivo_bloq) and (not turnos_conflicto or confirmar_con_turnos)
        
        if st.button("💾 Guardar bloqueo", type="primary", disabled=not puede_guardar_bloq, use_container_width=True, key="btn_guardar_bloqueo"):
            conn_ins = get_connection()
            cur_b = conn_ins.cursor()
            cur_b.execute(
                """INSERT INTO bloqueos_agenda (consultorio_id, fecha, hora_desde, hora_hasta, motivo, creado_por)
                   VALUES (%s, %s, %s, %s, %s, %s);""",
                (id_cons_bloq, fecha_bloq, t_desde, t_hasta, motivo_bloq, usuario_actual["id"])
            )
            conn_ins.commit()
            cur_b.close()
            conn_ins.close()
            st.success("Agenda tachada correctamente.")
            st.rerun()

        # Listado de bloqueos activos para la fecha seleccionada
        conn_b_list = get_connection()
        bloqueos_dia_sidebar = pd.read_sql(
            """SELECT b.id, b.consultorio_id, b.hora_desde, b.hora_hasta, b.motivo, c.nombre AS consultorio
               FROM bloqueos_agenda b
               JOIN consultorios c ON c.id = b.consultorio_id
               WHERE b.fecha = %s
               ORDER BY b.hora_desde;""",
            conn_b_list,
            params=(fecha,)
        )
        conn_b_list.close()
        
        if not bloqueos_dia_sidebar.empty:
            st.markdown("---")
            st.markdown(f"**Bloqueos activos ({fecha.strftime('%d/%m')}):**")
            for _, b_item in bloqueos_dia_sidebar.iterrows():
                r_str = f"{b_item['hora_desde'].strftime('%H:%M')} a {b_item['hora_hasta'].strftime('%H:%M')}"
                col_b_info, col_b_del = st.columns([3, 1])
                with col_b_info:
                    st.caption(f"🚫 **{b_item['consultorio']}** ({r_str})\n*{b_item['motivo']}*")
                with col_b_del:
                    if st.button("🗑️", key=f"del_bloq_sb_{b_item['id']}", help="Eliminar bloqueo"):
                        conn_del = get_connection()
                        cur_d = conn_del.cursor()
                        cur_d.execute("DELETE FROM bloqueos_agenda WHERE id = %s;", (b_item["id"],))
                        conn_del.commit()
                        cur_d.close()
                        conn_del.close()
                        st.rerun()

dia_semana = fecha.isoweekday()

if usuario_actual["rol"] == "profesional" and usuario_actual["profesional_id"] is not None:
    c_prop = get_connection()
    consultorios_propios = pd.read_sql(
        """SELECT DISTINCT consultorio_id FROM horarios_atencion
           WHERE profesional_id = %s AND dia_semana = %s;""",
        c_prop, params=(usuario_actual["profesional_id"], dia_semana),
    )
    c_prop.close()
    ids_propios = consultorios_propios["consultorio_id"].tolist()
    consultorios_df = consultorios_df[consultorios_df["id"].isin(ids_propios)].reset_index(drop=True)

horarios_df = cargar_horarios_dia(dia_semana)

conn = get_connection()

turnos_df = pd.read_sql(
    """
    SELECT t.id, t.consultorio_id, t.hora, t.paciente_id, t.profesional_id, t.estado,
           COALESCE(pac.apellido, '') AS apellido_paciente,
           COALESCE(pac.nombre, '(sin paciente)') AS paciente,
           pac.dni AS dni,
           pac.telefono AS telefono,
           COALESCE(os.nombre, 'Sin obra social') AS obra_social,
           COALESCE(s.nombre, '') AS servicio,
           COALESCE(s.indicaciones_preparacion, '') AS indicaciones_preparacion,
           p.nombre AS profesional,
           t.creado_en,
           uc.nombre_completo AS creado_por_nombre,
           um.nombre_completo AS modificado_por_nombre,
           t.modificado_en,
           t.traer_dinero,
           t.traer_credencial,
           t.traer_bonos,
           t.traer_ordenes
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

bloqueos_df = pd.read_sql(
    """
    SELECT b.id, b.consultorio_id, b.fecha, b.hora_desde, b.hora_hasta, b.motivo,
           u.nombre_completo AS creado_por_nombre, b.creado_en
    FROM bloqueos_agenda b
    LEFT JOIN usuarios u ON u.id = b.creado_por
    WHERE b.fecha = %s
    ORDER BY b.hora_desde;
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

if not bloqueos_df.empty:
    b_min = bloqueos_df["hora_desde"].min()
    b_max = bloqueos_df["hora_hasta"].max()
    if pd.notna(b_min) and b_min < hora_inicio:
        hora_inicio = b_min
    if pd.notna(b_max) and b_max > hora_fin:
        hora_fin = b_max

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

ALTO_FILA = 24
ALTO_ENCABEZADO = 48
es_hoy = (fecha == date.today())
hora_inicio_grilla = filas_horas[0] if filas_horas else None
total_franjas = len(filas_horas)

# -------------------------------------------------------------
# CONSTRUCCIÓN DE COLUMNAS INDEPENDIENTES POR CONSULTORIO
# -------------------------------------------------------------
columnas_html = []

for _, cons in consultorios_df.iterrows():
    cons_id = int(cons["id"])
    cons_nombre = cons["nombre"]
    h_cons = horarios_df[horarios_df["consultorio_id"] == cons_id].sort_values("hora_desde")
    t_cons = turnos_df[turnos_df["consultorio_id"] == cons_id]
    b_cons = bloqueos_df[bloqueos_df["consultorio_id"] == cons_id] if not bloqueos_df.empty else pd.DataFrame()

    cant_turnos = len(t_cons["paciente_id"].dropna().unique()) if not t_cons.empty else 0
    badge_turnos = f"{cant_turnos} turnos" if cant_turnos > 0 else "0 turnos"

    # Si el consultorio no tiene atención, ni turnos, ni bloqueos hoy
    if h_cons.empty and t_cons.empty and b_cons.empty:
        col_html = f"""
        <div class="columna-consultorio">
            <div class="header-consultorio">
                <span class="titulo-cons">{cons_nombre}</span>
                <span class="badge-cant vacio">Sin atención</span>
            </div>
            <div class="scroll-consultorio" data-cons-id="{cons_id}">
                <div class="sin-atencion-box">
                    <div class="icono-vacio">🏥</div>
                    <div style="font-size:12.5px;color:#94a3b8;font-weight:600;">Sin profesionales asignados hoy</div>
                </div>
            </div>
        </div>
        """
        columnas_html.append(col_html)
        continue

    # Turnos indexados por hora
    turnos_dict = {}
    for _, t in t_cons.iterrows():
        turnos_dict.setdefault(t["hora"], []).append(t)

    # Horarios del consultorio
    turnos_atencion = []
    for _, row in h_cons.iterrows():
        turnos_atencion.append({
            "profesional": row["profesional"],
            "hora_desde": row["hora_desde"],
            "hora_hasta": row["hora_hasta"],
        })

    def profesionales_en_hora(h):
        return [ta["profesional"] for ta in turnos_atencion if ta["hora_desde"] <= h < ta["hora_hasta"]]

    # Mapa de horas donde inicia la atención de un profesional
    divisores_prof = {}
    for ta in turnos_atencion:
        hd = ta["hora_desde"]
        if hd not in divisores_prof:
            divisores_prof[hd] = []
        divisores_prof[hd].append({
            "profesional": ta["profesional"],
            "desde": ta["hora_desde"].strftime("%H:%M"),
            "hasta": ta["hora_hasta"].strftime("%H:%M")
        })

    filas_cons_html = []
    skip_slots = 0
    en_intervalo = False

    for idx, h in enumerate(filas_horas):
        h_str = h.strftime("%H:%M")
        es_en_punto = (h.minute == 0)
        clase_en_punto = " hora-en-punto" if es_en_punto else ""

        # 1. DIVISOR DE PROFESIONAL (encabezado cuando arranca un profesional en este consultorio)
        if h in divisores_prof:
            items_doc = []
            for d in divisores_prof[h]:
                items_doc.append(f"<span class='nombre-prof'>{d['profesional']}</span> <span class='rango-prof'>{d['desde']} a {d['hasta']}</span>")
            banner_contenido = " &bull; ".join(items_doc)
            filas_cons_html.append(f"""
                <tr class="fila-divisor">
                    <td colspan="2" class="celda-divisor">
                        <div class="divisor-profesional">
                            <span class="icono-prof">🩺</span>
                            <div class="info-prof">{banner_contenido}</div>
                        </div>
                    </td>
                </tr>
            """)
            en_intervalo = False

        profs_activos = profesionales_en_hora(h)
        hay_atencion = len(profs_activos) > 0

        # 2. DIVISOR DE INTERVALO / FIN DE ATENCIÓN
        if not hay_atencion and not en_intervalo and any(ta["hora_hasta"] == h for ta in turnos_atencion):
            proximos = [ta for ta in turnos_atencion if ta["hora_desde"] > h]
            if proximos:
                prox_inicio = min(p["hora_desde"] for p in proximos)
                filas_cons_html.append(f"""
                    <tr class="fila-divisor fila-intervalo">
                        <td colspan="2" class="celda-divisor">
                            <div class="divisor-pausa">
                                ☕ <b>Intervalo</b> ({h_str} a {prox_inicio.strftime('%H:%M')})
                            </div>
                        </td>
                    </tr>
                """)
                en_intervalo = True
            else:
                filas_cons_html.append(f"""
                    <tr class="fila-divisor fila-intervalo">
                        <td colspan="2" class="celda-divisor">
                            <div class="divisor-pausa fin-atencion">
                                🏁 <b>Fin de atención</b> ({h_str})
                            </div>
                        </td>
                    </tr>
                """)
                en_intervalo = True

        if skip_slots > 0:
            skip_slots -= 1
            filas_cons_html.append(f'<tr class="fila-slot{clase_en_punto}"><td class="hora-cell">{h_str}</td></tr>')
            continue

        # 3. TURNO(S) OCUPADO(S) (Soporte para turnos únicos o superpuestos/simultáneos)
        if h in turnos_dict:
            turnos_en_h = turnos_dict[h]
            spans_citas = []
            tarjetas_html = []

            # Agrupar turnos en este horario por cita
            citas_unicas = {}
            for t_item in turnos_en_h:
                c_key = (
                    t_item.get("paciente_id") if pd.notna(t_item.get("paciente_id")) else t_item.get("paciente"),
                    t_item.get("profesional_id"),
                    t_item.get("servicio_id"),
                    t_item.get("creado_en")
                )
                if c_key not in citas_unicas:
                    citas_unicas[c_key] = t_item

            for c_key, t in citas_unicas.items():
                span = 1
                k = idx + 1
                while k < len(filas_horas) and filas_horas[k] in turnos_dict:
                    en_k = [
                        t2 for t2 in turnos_dict[filas_horas[k]]
                        if (
                            (t2.get("paciente_id") if pd.notna(t2.get("paciente_id")) else t2.get("paciente")) == c_key[0]
                            and t2.get("profesional_id") == c_key[1]
                            and t2.get("servicio_id") == c_key[2]
                        )
                    ]
                    if en_k:
                        span += 1
                        k += 1
                    else:
                        break
                spans_citas.append(span)

                # IDs de todos los slots de esta cita
                ids_bloque = []
                for x in range(idx, idx + span):
                    if x < len(filas_horas) and filas_horas[x] in turnos_dict:
                        for t_sub in turnos_dict[filas_horas[x]]:
                            if (
                                (t_sub.get("paciente_id") if pd.notna(t_sub.get("paciente_id")) else t_sub.get("paciente")) == c_key[0]
                                and t_sub.get("profesional_id") == c_key[1]
                                and t_sub.get("servicio_id") == c_key[2]
                            ):
                                ids_bloque.append(str(t_sub["id"]))

                tel = t["telefono"] if t["telefono"] else "sin tel."
                servicio = t["servicio"] if t["servicio"] else "Consulta"

                # Formatear requisitos que debe traer
                items_traer = []
                if pd.notna(t.get("traer_dinero")) and str(t.get("traer_dinero")).strip():
                    val_dinero = str(t.get("traer_dinero")).strip()
                    if not val_dinero.startswith("$"):
                        val_dinero = f"${val_dinero}"
                    items_traer.append(f"Abonar {val_dinero}")
                if t.get("traer_credencial") is True:
                    items_traer.append("Credencial / Carnet")
                if pd.notna(t.get("traer_bonos")) and int(t.get("traer_bonos", 0)) > 0:
                    cb = int(t.get("traer_bonos"))
                    items_traer.append(f"{cb} bono{'s' if cb > 1 else ''}")
                if pd.notna(t.get("traer_ordenes")) and int(t.get("traer_ordenes", 0)) > 0:
                    co = int(t.get("traer_ordenes"))
                    items_traer.append(f"{co} orden{'es' if co > 1 else ''}")

                tooltip = f"Tel: {tel} · {t['obra_social']}"
                if items_traer:
                    tooltip += " · Traer: " + ", ".join(items_traer)
                if t["modificado_por_nombre"] and pd.notna(t["modificado_en"]):
                    tooltip += f" · Modificado por {t['modificado_por_nombre']} el {t['modificado_en'].strftime('%d/%m %H:%M')}"
                elif t["creado_por_nombre"]:
                    tooltip += f" · Cargado por {t['creado_por_nombre']}"

                nombre_completo = f"{t['apellido_paciente']}, {t['paciente']}".strip(", ").upper()

                dt_inicio_turno = a_datetime(h)
                dt_fin_turno = dt_inicio_turno + timedelta(minutes=5 * span)
                rango_texto = f"{dt_inicio_turno.strftime('%H:%M')} a {dt_fin_turno.strftime('%H:%M')}"
                duracion_min_total = span * 5

                rango_badge_html = (
                    f'<div class="rango-turno">🕒 {rango_texto} ({duracion_min_total} min)</div>'
                    if span >= 3
                    else ""
                )

                badge_traer_html = (
                    f'<div class="traer-turno">📌 Traer: {", ".join(items_traer)}</div>'
                    if (items_traer and span >= 4)
                    else ""
                )

                def val_limpio(v, default="—"):
                    if pd.isna(v) or v is None:
                        return default
                    s = str(v).strip()
                    return s if s else default

                detalle = {
                    "nombre": nombre_completo,
                    "dni": val_limpio(t.get("dni")),
                    "telefono": val_limpio(tel, default="sin tel."),
                    "obra_social": val_limpio(t.get("obra_social"), default="Particular"),
                    "profesional": val_limpio(t.get("profesional")),
                    "servicio": servicio,
                    "consultorio": cons_nombre,
                    "hora": h_str,
                    "fecha": fecha.strftime("%d/%m/%Y"),
                    "estado": val_limpio(t.get("estado"), default="pendiente"),
                    "creado_por": val_limpio(t.get("creado_por_nombre")),
                    "creado_en": t["creado_en"].strftime("%d/%m/%Y %H:%M") if pd.notna(t.get("creado_en")) and hasattr(t["creado_en"], "strftime") else "—",
                    "modificado_por": val_limpio(t.get("modificado_por_nombre")),
                    "modificado_en": t["modificado_en"].strftime("%d/%m/%Y %H:%M") if pd.notna(t.get("modificado_en")) and hasattr(t["modificado_en"], "strftime") else "—",
                    "historial": historial_por_paciente.get(int(t["paciente_id"]), []) if pd.notna(t.get("paciente_id")) else [],
                    "items_traer": items_traer,
                    "indicaciones_preparacion": val_limpio(t.get("indicaciones_preparacion"), default=""),
                }
                detalle_b64 = base64.b64encode(json.dumps(detalle, ensure_ascii=False).encode("utf-8")).decode("ascii")

                alto_tarjeta_px = (span * ALTO_FILA - 3) if len(citas_unicas) == 1 else "auto"
                style_alto = f"height: {alto_tarjeta_px}px; min-height: {alto_tarjeta_px}px;" if len(citas_unicas) == 1 else "margin-bottom: 3px;"

                tarjetas_html.append(f"""
                    <div class="tarjeta-turno {clase_estado(t['estado'])}" style="{style_alto}" data-ids="{','.join(ids_bloque)}" data-estado="{t['estado']}">
                        <div class="barra-estado"></div>
                        <div class="contenido-turno" data-detalle="{detalle_b64}">
                            <div class="nombre-paciente">{nombre_completo}</div>
                            <div class="detalle-turno">{t['profesional']}: {servicio}</div>
                            {rango_badge_html}
                            {badge_traer_html}
                            <div class="btn-recordatorio-chip" title="Ver recordatorio y WhatsApp">💬 Recordatorio</div>
                        </div>
                    </div>
                """)

            span_max = max(spans_citas) if spans_citas else 1
            skip_slots = span_max - 1

            filas_cons_html.append(f"""
                <tr class="fila-slot{clase_en_punto}">
                    <td class="hora-cell">{h_str}</td>
                    <td class="celda-turno" rowspan="{span_max}" style="height: {span_max * ALTO_FILA}px;" title="{tooltip}">
                        {''.join(tarjetas_html)}
                    </td>
                </tr>
            """)
            continue

        # 4. TACHAR AGENDA (BLOQUEO DE CONSULTORIO)
        bloqueo_activo = None
        if not b_cons.empty:
            b_matches = b_cons[(b_cons["hora_desde"] <= h) & (h < b_cons["hora_hasta"])]
            if not b_matches.empty:
                bloqueo_activo = b_matches.iloc[0]

        if bloqueo_activo is not None:
            span_b = 1
            k = idx + 1
            while k < len(filas_horas):
                h_k = filas_horas[k]
                if h_k in turnos_dict:
                    break
                if not (bloqueo_activo["hora_desde"] <= h_k < bloqueo_activo["hora_hasta"]):
                    break
                span_b += 1
                k += 1
            skip_slots = span_b - 1

            alto_bloq_px = span_b * ALTO_FILA - 3
            hd_str = bloqueo_activo["hora_desde"].strftime("%H:%M") if hasattr(bloqueo_activo["hora_desde"], "strftime") else str(bloqueo_activo["hora_desde"])[:5]
            hh_str = bloqueo_activo["hora_hasta"].strftime("%H:%M") if hasattr(bloqueo_activo["hora_hasta"], "strftime") else str(bloqueo_activo["hora_hasta"])[:5]
            rango_bloqueo = f"{hd_str} a {hh_str}"

            filas_cons_html.append(f"""
                <tr class="fila-slot{clase_en_punto}">
                    <td class="hora-cell">{h_str}</td>
                    <td class="celda-turno" rowspan="{span_b}" style="height: {span_b * ALTO_FILA}px;">
                        <div class="tarjeta-bloqueo" style="height: {alto_bloq_px}px; min-height: {alto_bloq_px}px;"
                             data-bloqueo-id="{bloqueo_activo['id']}"
                             data-motivo="{bloqueo_activo['motivo']}"
                             data-rango="{rango_bloqueo}"
                             data-cons-nombre="{cons_nombre}"
                             title="Consultorio bloqueado ({rango_bloqueo}): {bloqueo_activo['motivo']}. Haz click para ver detalles o eliminar.">
                            <div class="barra-bloqueo"></div>
                            <div class="bloqueo-contenido">
                                <div class="bloqueo-titulo">🚫 AGENDA BLOQUEADA</div>
                                <div class="bloqueo-motivo">{bloqueo_activo['motivo']}</div>
                                <div class="bloqueo-rango">🕒 {rango_bloqueo}</div>
                            </div>
                        </div>
                    </td>
                </tr>
            """)
            continue

        # 5. CASILLERO LIBRE O FUERA DE HORARIO
        if hay_atencion:
            filas_cons_html.append(f"""
                <tr class="fila-slot{clase_en_punto}">
                    <td class="hora-cell">{h_str}</td>
                    <td class="libre" data-hora="{h_str}" data-cons-id="{cons_id}" data-cons-nombre="{cons_nombre}" title="Click para nuevo turno ({h_str} - {cons_nombre})">
                        <span class="slot-libre-plus">+</span>
                    </td>
                </tr>
            """)
        else:
            filas_cons_html.append(f"""
                <tr class="fila-slot slot-inactivo{clase_en_punto}">
                    <td class="hora-cell inactivo">{h_str}</td>
                    <td class="libre libre-inactiva" data-hora="{h_str}" data-cons-id="{cons_id}" data-cons-nombre="{cons_nombre}" title="Fuera de horario · Click para turno extraordinario ({h_str})">
                        <span class="slot-libre-plus">+</span>
                    </td>
                </tr>
            """)

    tabla_body = "\n".join(filas_cons_html)
    col_html = f"""
    <div class="columna-consultorio">
        <div class="header-consultorio">
            <span class="titulo-cons">{cons_nombre}</span>
            <span class="badge-cant">{badge_turnos}</span>
        </div>
        <div class="scroll-consultorio" data-cons-id="{cons_id}">
            <table class="tabla-cons">
                <tbody>
                    {tabla_body}
                </tbody>
            </table>
        </div>
    </div>
    """
    columnas_html.append(col_html)

tabla_html = f"""
<style>
body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: transparent;
}}
.tablero-consultorios {{
    display: flex;
    flex-direction: row;
    gap: 14px;
    align-items: stretch;
    width: 100%;
    overflow-x: auto;
    padding: 4px 2px 14px 2px;
    box-sizing: border-box;
}}
.columna-consultorio {{
    flex: 1 1 280px;
    min-width: 270px;
    max-width: 380px;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.04);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}}
.header-consultorio {{
    padding: 10px 14px;
    background: #f8fafc;
    border-bottom: 2px solid #e2e8f0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
}}
.header-consultorio .titulo-cons {{
    font-size: 15px;
    font-weight: 700;
    color: #0f172a;
    letter-spacing: -0.01em;
}}
.header-consultorio .badge-cant {{
    font-size: 11px;
    font-weight: 600;
    color: #475569;
    background: #e2e8f0;
    padding: 3px 8px;
    border-radius: 12px;
}}
.header-consultorio .badge-cant.vacio {{
    background: #f1f5f9;
    color: #94a3b8;
}}
.scroll-consultorio {{
    height: 640px;
    min-height: 640px;
    overflow-y: scroll;
    overflow-x: hidden;
    position: relative;
    background: #ffffff;
}}
.scroll-consultorio::-webkit-scrollbar {{
    width: 6px;
}}
.scroll-consultorio::-webkit-scrollbar-track {{
    background: #f8fafc;
}}
.scroll-consultorio::-webkit-scrollbar-thumb {{
    background: #cbd5e1;
    border-radius: 4px;
}}
.scroll-consultorio::-webkit-scrollbar-thumb:hover {{
    background: #94a3b8;
}}
.tabla-cons {{
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed;
    font-size: 12px;
}}
.hora-cell {{
    width: 48px;
    min-width: 48px;
    max-width: 48px;
    padding: 0 4px;
    text-align: center;
    font-size: 10.5px;
    font-weight: 600;
    color: #94a3b8;
    background: #fafbfc;
    border-right: 1px solid #f1f5f9;
    border-bottom: 1px solid #f8fafc;
    height: 24px;
    box-sizing: border-box;
    vertical-align: middle;
    user-select: none;
}}
.hora-en-punto .hora-cell {{
    color: #334155;
    font-weight: 700;
    border-top: 1px solid #e2e8f0;
    background: #f1f5f9;
}}
.hora-en-punto td {{
    border-top: 1px solid #e2e8f0;
}}
.fila-divisor {{
    position: sticky;
    top: 0;
    z-index: 10;
}}
.celda-divisor {{
    padding: 0;
    border: none;
}}
.divisor-profesional {{
    background: #2563eb;
    color: #ffffff;
    padding: 7px 10px;
    font-size: 11.5px;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.12);
    letter-spacing: 0.01em;
}}
.divisor-profesional .icono-prof {{
    font-size: 14px;
}}
.divisor-profesional .info-prof {{
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}
.divisor-profesional .rango-prof {{
    font-size: 10.5px;
    font-weight: 500;
    background: rgba(255,255,255,0.22);
    padding: 2px 6px;
    border-radius: 4px;
    color: #ffffff;
}}
.divisor-pausa {{
    background: #f8fafc;
    color: #64748b;
    border-top: 1px dashed #cbd5e1;
    border-bottom: 1px dashed #cbd5e1;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 600;
    text-align: center;
}}
.divisor-pausa.fin-atencion {{
    background: #fef2f2;
    color: #b91c1c;
    border-color: #fecaca;
}}
.celda-turno {{
    padding: 1.5px 3px !important;
    border: none;
    vertical-align: top;
}}
.tarjeta-turno {{
    height: 100%;
    box-sizing: border-box;
    display: flex;
    align-items: stretch;
    overflow: hidden;
    border-radius: 7px;
    background: #f4f4f6;
    box-shadow: 0 1px 3px rgba(20,20,30,0.05);
    cursor: pointer;
    transition: transform 0.1s, box-shadow 0.1s;
}}
.tarjeta-turno:hover {{
    transform: translateY(-1px);
    box-shadow: 0 3px 8px rgba(20,20,30,0.12);
}}
.barra-estado {{
    width: 6px;
    flex-shrink: 0;
    background: #ccc;
    border-radius: 7px 0 0 7px;
    cursor: pointer;
    transition: width 0.15s ease;
}}
.barra-estado:hover {{
    width: 12px;
}}
.contenido-turno {{
    flex: 1;
    padding: 3px 6px;
    overflow: hidden;
    min-width: 0;
    cursor: pointer;
}}
.nombre-paciente {{
    font-weight: 700;
    text-transform: uppercase;
    font-size: 11.5px;
    color: #1f2937;
    line-height: 1.25;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.detalle-turno {{
    font-weight: 400;
    font-size: 10px;
    color: #6b7280;
    line-height: 1.25;
    margin-top: 1px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.rango-turno {{
    font-weight: 600;
    font-size: 9.5px;
    color: #4b5563;
    line-height: 1.25;
    margin-top: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.traer-turno {{
    font-weight: 600;
    font-size: 9.5px;
    color: #b45309;
    background: #fef3c7;
    border: 1px solid #fde68a;
    padding: 1px 5px;
    border-radius: 4px;
    line-height: 1.25;
    margin-top: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
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
    text-decoration: line-through;
    color: #9ca3af;
}}
.libre {{
    background: transparent;
    cursor: pointer;
    position: relative;
    transition: background 0.12s ease;
    border-bottom: 1px dashed #f1f5f9;
    height: 24px;
    box-sizing: border-box;
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
.libre-inactiva {{
    background: #fafbfc;
    border-bottom: 1px solid #f8fafc;
}}
.hora-cell.inactivo {{
    color: #cbd5e1;
}}
.sin-atencion-box {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 300px;
    color: #94a3b8;
    text-align: center;
    padding: 20px;
}}
.icono-vacio {{
    font-size: 36px;
    margin-bottom: 8px;
    opacity: 0.6;
}}
.tarjeta-bloqueo {{
    background: repeating-linear-gradient(-45deg, #f8fafc, #f8fafc 8px, #f1f5f9 8px, #f1f5f9 16px);
    border: 1.5px dashed #cbd5e1;
    border-radius: 8px;
    padding: 6px 10px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: center;
    position: relative;
    cursor: pointer;
    overflow: hidden;
    transition: all 0.15s ease;
}}
.tarjeta-bloqueo:hover {{
    background: repeating-linear-gradient(-45deg, #fef2f2, #fef2f2 8px, #fee2e2 8px, #fee2e2 16px);
    border-color: #f87171;
}}
.barra-bloqueo {{
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 4px;
    background: #ef4444;
}}
.bloqueo-contenido {{
    padding-left: 6px;
}}
.bloqueo-titulo {{
    font-size: 10px;
    font-weight: 800;
    color: #991b1b;
    letter-spacing: 0.02em;
    display: flex;
    align-items: center;
    gap: 4px;
}}
.bloqueo-motivo {{
    font-size: 11px;
    font-weight: 600;
    color: #334155;
    margin-top: 2px;
    line-height: 1.25;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}
.bloqueo-rango {{
    font-size: 9.5px;
    font-weight: 500;
    color: #64748b;
    margin-top: 2px;
}}
.btn-recordatorio-chip {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 9.5px;
    font-weight: 700;
    color: #15803d;
    background: #dcfce7;
    border: 1px solid #86efac;
    padding: 2px 7px;
    border-radius: 12px;
    cursor: pointer;
    margin-top: 4px;
    width: fit-content;
    transition: all 0.15s ease;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}}
.btn-recordatorio-chip:hover {{
    background: #bbf7d0;
    color: #166534;
    transform: scale(1.02);
}}
@media (max-width: 768px) {{
    .tablero-consultorios {{
        scroll-snap-type: x mandatory;
        gap: 10px;
    }}
    .columna-consultorio {{
        min-width: 86vw;
        max-width: 90vw;
        scroll-snap-align: start;
    }}
}}
</style>
<div class="tablero-consultorios">
{''.join(columnas_html)}
</div>
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
        if st.button("Cerrar", key="btn_cerrar_sin_prof"):
            cerrar_modal_turno()
            st.rerun()
        return

    idx_prof = 0
    if hora_inicial_str:
        try:
            h_init = datetime.strptime(hora_inicial_str, "%H:%M").time()
            profs_hora = horarios_cons[
                (horarios_cons["hora_desde"] <= h_init) & (h_init < horarios_cons["hora_hasta"])
            ]
            if not profs_hora.empty:
                prof_match = profs_hora.iloc[0]["profesional"]
                profs_list = profesionales_cons["profesional"].tolist()
                if prof_match in profs_list:
                    idx_prof = profs_list.index(prof_match)
        except Exception:
            pass

    with col2:
        if len(profesionales_cons) == 1:
            profesional_sel_nombre = profesionales_cons.iloc[0]["profesional"]
            profesional_id_sel = int(profesionales_cons.iloc[0]["profesional_id"])
            st.text_input("Profesional", value=profesional_sel_nombre, disabled=True)
        else:
            profesional_sel_nombre = st.selectbox("Profesional", options=profesionales_cons["profesional"], index=idx_prof)
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
        if st.button("Cerrar", key="btn_cerrar_sin_serv"):
            cerrar_modal_turno()
            st.rerun()
        return

    col3, col4 = st.columns(2)
    with col3:
        servicio_opciones = [f"{r['nombre']} ({r['duracion_minutos']} min)" for _, r in servicios_df.iterrows()]
        servicio_sel_str = st.selectbox("Servicio", options=servicio_opciones)
        servicio_row = servicios_df.iloc[servicio_opciones.index(servicio_sel_str)]
        servicio_id_sel = int(servicio_row["id"])
        duracion_min = int(servicio_row["duracion_minutos"])

    slots_necesarios = max(1, -(-duracion_min // 5))

    # Franjas disponibles según el horario del profesional
    if not horarios_cons_sel.empty:
        h_prof_min = horarios_cons_sel["hora_desde"].min()
        h_prof_max = horarios_cons_sel["hora_hasta"].max()
        franjas_prof = [h for h in filas_horas if h_prof_min <= h < h_prof_max]
    else:
        franjas_prof = filas_horas

    if not franjas_prof:
        franjas_prof = filas_horas

    opciones_horas = [h.strftime("%H:%M") for h in franjas_prof]

    idx_hora = 0
    if hora_inicial_str and hora_inicial_str in opciones_horas:
        idx_hora = opciones_horas.index(hora_inicial_str)

    with col4:
        if opciones_horas:
            hora_sel_str = st.selectbox("Horario", options=opciones_horas, index=idx_hora)
            hora_sel = datetime.strptime(hora_sel_str, "%H:%M").time()
        else:
            hora_sel = None
            st.warning("No hay horarios disponibles.")

    st.markdown("---")
    dni_input = st.text_input("DNI del paciente", key="modal_input_dni").strip()

    paciente_id_existente = None
    apellido_nuevo = nombre_nuevo = telefono_nuevo = ""
    obra_social_id_nueva = None

    if dni_input:
        conn_b = get_connection()
        res = pd.read_sql("SELECT id, apellido, nombre, telefono FROM pacientes WHERE dni = %s;", conn_b, params=(dni_input,))
        conn_b.close()
        if not res.empty:
            paciente_id_existente = int(res.iloc[0]["id"])
            st.success(f"Paciente: **{res.iloc[0]['nombre']} {res.iloc[0]['apellido']}** (Tel: {res.iloc[0]['telefono'] or 'sin registrar'})")
        else:
            st.info("Paciente nuevo no registrado. Complete sus datos para crearlo:")
            c1, c2, c3 = st.columns(3)
            with c1:
                apellido_nuevo = st.text_input("Apellido *", key="modal_input_apellido").strip()
            with c2:
                nombre_nuevo = st.text_input("Nombre *", key="modal_input_nombre").strip()
            with c3:
                telefono_nuevo = st.text_input("Teléfono", key="modal_input_telefono").strip()

            conn_os = get_connection()
            obras_sociales_df = pd.read_sql("SELECT id, nombre FROM obras_sociales ORDER BY nombre;", conn_os)
            conn_os.close()

            c4, c5 = st.columns([2, 1])
            with c4:
                opciones_os = ["— Elegir —"] + obras_sociales_df["nombre"].tolist() + ["➕ Agregar nueva..."]
                os_sel = st.selectbox("Obra social", options=opciones_os, key="modal_sel_os")
            with c5:
                if os_sel == "➕ Agregar nueva...":
                    os_nueva_nombre = st.text_input("Nueva obra social", key="modal_input_nueva_os").strip()
                    if os_nueva_nombre:
                        conn_os2 = get_connection()
                        cur_os = conn_os2.cursor()
                        cur_os.execute(
                            "INSERT INTO obras_sociales (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING RETURNING id;",
                            (os_nueva_nombre,),
                        )
                        fila_os = cur_os.fetchone()
                        if fila_os is None:
                            cur_os.execute("SELECT id FROM obras_sociales WHERE nombre = %s;", (os_nueva_nombre,))
                            fila_os = cur_os.fetchone()
                        conn_os2.commit()
                        obra_social_id_nueva = int(fila_os[0])
                        cur_os.close()
                        conn_os2.close()
                elif os_sel != "— Elegir —":
                    obra_social_id_nueva = int(obras_sociales_df.loc[obras_sociales_df["nombre"] == os_sel, "id"].iloc[0])

    st.markdown("---")
    st.markdown("##### 📋 Lo que debe traer el paciente al turno")
    c_req1, c_req2 = st.columns(2)
    with c_req1:
        traer_dinero = st.text_input("💵 Dinero / Coseguro a abonar", placeholder="Ej: $5000 o Efectivo", key="input_traer_dinero")
        traer_credencial = st.checkbox("💳 Traer credencial / carnet de obra social", value=True, key="check_traer_cred")
    with c_req2:
        col_bon_chk, col_bon_num = st.columns([1, 1.2])
        with col_bon_chk:
            check_bonos = st.checkbox("📑 Traer Bonos", key="check_bonos")
        with col_bon_num:
            if check_bonos:
                cant_bonos = int(st.number_input("¿Cuántos bonos?", min_value=1, max_value=20, value=1, step=1, key="num_bonos"))
            else:
                cant_bonos = 0

        col_ord_chk, col_ord_num = st.columns([1, 1.2])
        with col_ord_chk:
            check_ordenes = st.checkbox("📝 Traer Órdenes", key="check_ordenes")
        with col_ord_num:
            if check_ordenes:
                cant_ordenes = int(st.number_input("¿Cuántas órdenes?", min_value=1, max_value=20, value=1, step=1, key="num_ordenes"))
            else:
                cant_ordenes = 0

    # -------------------------------------------------------------
    # VALIDACIONES DE SUPERPOSICIÓN / BLOQUEO
    # -------------------------------------------------------------
    confirma_superposicion = True
    confirma_bloqueo = True

    if hora_sel is not None:
        dt_inicio = a_datetime(hora_sel)
        horas_a_reservar = [(dt_inicio + timedelta(minutes=5 * i)).time() for i in range(slots_necesarios)]
        hora_fin_calc = (dt_inicio + timedelta(minutes=5 * slots_necesarios)).time()

        # 1. Advertencia de turnos existentes en ese consultorio y franja
        turnos_conflicto_cons = turnos_cons_sel[turnos_cons_sel["hora"].isin(horas_a_reservar)]
        if not turnos_conflicto_cons.empty:
            citas_conf = turnos_conflicto_cons[["paciente", "apellido_paciente", "hora", "profesional"]].drop_duplicates()
            detalles_c = [
                f"{r['apellido_paciente']}, {r['paciente']} ({r['hora'].strftime('%H:%M') if hasattr(r['hora'], 'strftime') else str(r['hora'])[:5]} hs · Dr/a. {r['profesional']})"
                for _, r in citas_conf.iterrows()
            ]
            st.warning(f"⚠️ **Atención:** En este horario ya existe turno agendado en este consultorio:\n• " + "\n• ".join(detalles_c))
            confirma_superposicion = st.checkbox("☑️ Deseo agendar este turno superpuesto / simultáneo igualmente", key="chk_conf_superposicion")

        # 2. Advertencia de bloqueos de agenda en este consultorio y franja
        bloqueos_conflicto_cons = bloqueos_df[
            (bloqueos_df["consultorio_id"] == cons_id_sel) &
            (bloqueos_df["hora_desde"] < hora_fin_calc) &
            (bloqueos_df["hora_hasta"] > hora_sel)
        ]
        if not bloqueos_conflicto_cons.empty:
            b_c = bloqueos_conflicto_cons.iloc[0]
            hd_c = b_c["hora_desde"].strftime("%H:%M") if hasattr(b_c["hora_desde"], "strftime") else str(b_c["hora_desde"])[:5]
            hh_c = b_c["hora_hasta"].strftime("%H:%M") if hasattr(b_c["hora_hasta"], "strftime") else str(b_c["hora_hasta"])[:5]
            st.warning(f"🚫 **Atención:** La agenda de este consultorio está bloqueada/tachada ({hd_c} a {hh_c} hs) por: *{b_c['motivo']}*.")
            confirma_bloqueo = st.checkbox("☑️ Deseo agendar el turno dentro de la franja bloqueada igualmente", key="chk_conf_bloqueo")

    puede_guardar = bool(
        dni_input
        and hora_sel is not None
        and (paciente_id_existente is not None or (apellido_nuevo and nombre_nuevo))
        and confirma_superposicion
        and confirma_bloqueo
    )

    c_btn1, c_btn2 = st.columns([3, 1])
    with c_btn1:
        if st.button("💾 Guardar turno", type="primary", disabled=not puede_guardar, use_container_width=True, key="btn_guardar_turno"):
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
                                                servicio_id, estado, creado_por,
                                                traer_dinero, traer_credencial, traer_bonos, traer_ordenes)
                           VALUES (%s,%s,%s,%s,%s,%s,'pendiente',%s,%s,%s,%s,%s);""",
                        (fecha, h, profesional_id_sel, cons_id_sel, paciente_id, servicio_id_sel, usuario_actual["id"],
                         traer_dinero.strip() if traer_dinero else None,
                         traer_credencial,
                         cant_bonos,
                         cant_ordenes),
                    )
                conn_w.commit()
                cerrar_modal_turno()
                st.rerun()
            except psycopg2.errors.UniqueViolation:
                conn_w.rollback()
                st.error("Ese horario ya fue ocupado.")
            except Exception as e:
                conn_w.rollback()
                st.error(f"Error al guardar turno: {e}")
            finally:
                cur.close()
                conn_w.close()
    with c_btn2:
        if st.button("Cancelar", use_container_width=True, key="btn_cancelar_turno"):
            cerrar_modal_turno()
            st.rerun()

    if not puede_guardar:
        motivos = []
        if not dni_input:
            motivos.append("ingresar el DNI del paciente")
        elif paciente_id_existente is None:
            if not apellido_nuevo:
                motivos.append("completar el Apellido")
            if not nombre_nuevo:
                motivos.append("completar el Nombre")
        if hora_sel is None:
            motivos.append("seleccionar un Horario")
        elif not confirma_superposicion:
            motivos.append("tildar la casilla para confirmar el turno superpuesto")
        elif not confirma_bloqueo:
            motivos.append("tildar la casilla para confirmar el turno dentro del bloqueo")
        if motivos:
            st.caption(f"💡 Para guardar debe: {', '.join(motivos)}.")

def cerrar_modal_turno():
    st.session_state["mostrar_modal_turno"] = False
    st.session_state["modal_cons_id"] = None
    st.session_state["modal_hora"] = None

def abrir_modal_turno(cons_id=None, hora=None):
    # Limpiar inputs previos para que el formulario se abra limpio
    for k in [
        "modal_input_dni", "modal_input_apellido", "modal_input_nombre",
        "modal_input_telefono", "modal_sel_os", "modal_input_nueva_os",
        "input_traer_dinero", "check_traer_cred", "check_bonos", "num_bonos",
        "check_ordenes", "num_ordenes"
    ]:
        if k in st.session_state:
            del st.session_state[k]
    st.session_state["modal_cons_id"] = cons_id
    st.session_state["modal_hora"] = hora
    st.session_state["mostrar_modal_turno"] = True

# Definición del modal según soporte de Streamlit
if hasattr(st, "dialog"):
    import inspect
    sig = inspect.signature(st.dialog)
    if "on_dismiss" in sig.parameters:
        @st.dialog("Cargar Turno", width="large", on_dismiss=cerrar_modal_turno)
        def abrir_dialogo_turno():
            modal_contenido_nuevo_turno(
                cons_id_inicial=st.session_state.get("modal_cons_id"),
                hora_inicial_str=st.session_state.get("modal_hora"),
            )
    else:
        @st.dialog("Cargar Turno", width="large")
        def abrir_dialogo_turno():
            modal_contenido_nuevo_turno(
                cons_id_inicial=st.session_state.get("modal_cons_id"),
                hora_inicial_str=st.session_state.get("modal_hora"),
            )

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
        if st.button("➕  Nuevo Turno", type="primary", use_container_width=True, key="btn_nuevo_turno_top"):
            abrir_modal_turno()
            st.rerun()

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

    # Manejo de clics (estados, borrado, click en celda libre o en bloqueo)
    if resultado_click and resultado_click.get("ts") != st.session_state.get("_ultimo_click_ts"):
        st.session_state["_ultimo_click_ts"] = resultado_click["ts"]
        
        tipo_accion = resultado_click.get("tipo")
        
        # 1. Click en celda libre -> Abrir modal con hora y consultorio inmediatamente
        if tipo_accion == "nuevo_turno":
            h_click = resultado_click.get("hora")
            c_click = resultado_click.get("consultorio_id")
            abrir_modal_turno(cons_id=c_click, hora=h_click)
            st.rerun()

        # 2. Click en bloqueo de agenda
        elif tipo_accion == "click_bloqueo":
            st.session_state["bloqueo_seleccionado"] = {
                "id": resultado_click.get("bloqueo_id"),
                "motivo": resultado_click.get("motivo"),
                "rango": resultado_click.get("rango"),
                "consultorio": resultado_click.get("consultorio"),
            }
            st.rerun()

        # 3. Eliminación
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

        # 4. Cambio de estado
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

    # RENDERIZADO DEL MODAL SI ESTÁ ACTIVO
    if st.session_state.get("mostrar_modal_turno"):
        if hasattr(st, "dialog"):
            abrir_dialogo_turno()
        else:
            with st.expander("➕ Cargar nuevo turno", expanded=True):
                modal_contenido_nuevo_turno(
                    cons_id_inicial=st.session_state.get("modal_cons_id"),
                    hora_inicial_str=st.session_state.get("modal_hora")
                )

    # MODAL DE DETALLE / ELIMINACIÓN DE BLOQUEO (AGENDA TACHADA)
    if st.session_state.get("bloqueo_seleccionado"):
        bloq = st.session_state["bloqueo_seleccionado"]
        if hasattr(st, "dialog"):
            @st.dialog("🚫 Agenda Bloqueada / Tachada")
            def dialog_ver_bloqueo():
                st.markdown(f"**Consultorio:** {bloq.get('consultorio', 'Consultorio')}")
                st.markdown(f"**Horario:** 🕒 {bloq.get('rango', '')}")
                st.markdown(f"**Motivo:** {bloq.get('motivo', '')}")
                st.markdown("---")
                c_del, c_close = st.columns([1.5, 1])
                with c_del:
                    if st.button("🗑️ Eliminar bloqueo", type="primary", use_container_width=True, key="btn_del_bloq_dialog"):
                        conn_del = get_connection()
                        cur_del = conn_del.cursor()
                        cur_del.execute("DELETE FROM bloqueos_agenda WHERE id = %s;", (bloq["id"],))
                        conn_del.commit()
                        cur_del.close()
                        conn_del.close()
                        st.session_state["bloqueo_seleccionado"] = None
                        st.success("Bloqueo eliminado correctamente.")
                        st.rerun()
                with c_close:
                    if st.button("Cerrar", use_container_width=True, key="btn_close_bloq_dialog"):
                        st.session_state["bloqueo_seleccionado"] = None
                        st.rerun()
            dialog_ver_bloqueo()

    st.caption("⚡ Haz click en un casillero vacío para agregar un turno, en 💬 Recordatorio para abrir el mensaje de WhatsApp, o en la barra de color para cambiar su estado.")

with tab_servicios:
    st.subheader("Administrar servicios")
    conn_s = get_connection()
    servicios_actuales = pd.read_sql(
        """SELECT s.id, p.nombre AS profesional, s.nombre AS servicio, s.duracion_minutos,
                  COALESCE(s.indicaciones_preparacion, '') AS indicaciones_preparacion,
                  s.profesional_id
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
            servicios_actuales[["profesional", "servicio", "duracion_minutos", "indicaciones_preparacion"]].rename(
                columns={
                    "profesional": "Profesional",
                    "servicio": "Servicio",
                    "duracion_minutos": "Duración (min)",
                    "indicaciones_preparacion": "Preparación previa / Indicaciones",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )

    st.markdown("#### ➕ Agregar nuevo servicio")
    c0, c1, c2 = st.columns([2, 3, 2])
    with c0:
        prof_nuevo_serv = st.selectbox("Profesional", options=todos_profesionales["nombre"], key="prof_nuevo_serv")
    with c1:
        nuevo_serv_nombre = st.text_input("Nombre del servicio", placeholder="Ej: Ecografía abdominal", key="nuevo_serv_nombre")
    with c2:
        nuevo_serv_duracion = st.number_input(
            "Duración (min, múltiplo de 5)", min_value=5, step=5, value=30, key="nuevo_serv_dur"
        )

    nuevo_serv_indicaciones = st.text_area(
        "Indicaciones especiales / Preparación previa (para recordatorio)",
        placeholder="Ej: Ayuno de 8 horas. Concurrir con vejiga llena.",
        help="Estas indicaciones se incluirán automáticamente en el recordatorio de WhatsApp del turno.",
        key="nuevo_serv_ind"
    )

    if st.button("Guardar nuevo servicio", type="primary", key="btn_agregar_servicio"):
        if nuevo_serv_nombre.strip():
            prof_id_nuevo_serv = int(
                todos_profesionales.loc[todos_profesionales["nombre"] == prof_nuevo_serv, "id"].iloc[0]
            )
            conn_s2 = get_connection()
            cur_s = conn_s2.cursor()
            cur_s.execute(
                """INSERT INTO servicios (nombre, duracion_minutos, profesional_id, indicaciones_preparacion)
                   VALUES (%s, %s, %s, %s);""",
                (nuevo_serv_nombre.strip(), int(nuevo_serv_duracion), prof_id_nuevo_serv, nuevo_serv_indicaciones.strip() or None),
            )
            conn_s2.commit()
            cur_s.close()
            conn_s2.close()
            st.success("Servicio agregado correctamente.")
            st.rerun()
        else:
            st.warning("Escribí un nombre para el servicio.")

    # Modificar servicio existente
    if not servicios_actuales.empty:
        st.markdown("---")
        with st.expander("✏️ Modificar servicio existente", expanded=False):
            opciones_serv_edit = [
                f"{r['servicio']} ({r['profesional']})" for _, r in servicios_actuales.iterrows()
            ]
            serv_edit_sel = st.selectbox("Seleccionar servicio a editar", options=opciones_serv_edit, key="sel_serv_edit")
            serv_edit_row = servicios_actuales.iloc[opciones_serv_edit.index(serv_edit_sel)]

            c_e1, c_e2 = st.columns([3, 2])
            with c_e1:
                edit_nombre = st.text_input("Nombre del servicio", value=serv_edit_row["servicio"], key="edit_serv_nom")
            with c_e2:
                edit_dur = st.number_input(
                    "Duración (min)", min_value=5, step=5, value=int(serv_edit_row["duracion_minutos"]), key="edit_serv_dur"
                )

            edit_ind = st.text_area(
                "Indicaciones especiales / Preparación previa (para recordatorio)",
                value=serv_edit_row["indicaciones_preparacion"],
                placeholder="Ej: Ayuno de 8 horas. Concurrir con vejiga llena.",
                key="edit_serv_ind"
            )

            if st.button("💾 Guardar cambios en el servicio", type="primary", key="btn_save_edit_serv"):
                if edit_nombre.strip():
                    conn_edit = get_connection()
                    cur_e = conn_edit.cursor()
                    cur_e.execute(
                        """UPDATE servicios
                           SET nombre = %s, duracion_minutos = %s, indicaciones_preparacion = %s
                           WHERE id = %s;""",
                        (edit_nombre.strip(), int(edit_dur), edit_ind.strip() or None, int(serv_edit_row["id"])),
                    )
                    conn_edit.commit()
                    cur_e.close()
                    conn_edit.close()
                    st.success("Servicio actualizado correctamente.")
                    st.rerun()
                else:
                    st.warning("El servicio debe tener un nombre.")

with tab_pacientes:
    st.subheader("Pacientes")
    st.info("Todavía no armamos esta sección — la vamos a construir con la referencia que me pases de cómo la querés.")
    conn_p = get_connection()
    total_pac = pd.read_sql("SELECT count(*) AS total FROM pacientes;", conn_p).iloc[0]["total"]
    conn_p.close()
    st.caption(f"Por ahora, hay {total_pac} pacientes cargados en la base.")
