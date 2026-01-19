import os
import json
import cloudinary
import cloudinary.uploader
import cloudinary.api
import pandas as pd
import requests
import io
import mysql.connector
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask import send_from_directory
from flask import render_template
from datetime import datetime

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')


cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)


UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# 🔌 Conexión MySQL
def conexion_mysql():
    host = os.environ.get("MYSQLHOST")
    if not host:
        raise Exception("MYSQLHOST no definido en variables de entorno")
    
    return mysql.connector.connect(
        
        host=host,
        user=os.environ.get("MYSQLUSER"),
        password=os.environ.get("MYSQLPASSWORD"),
        database=os.environ.get("MYSQLDATABASE"),
        port=int(os.environ.get("MYSQLPORT", 3306))
    )

def subir_a_cloudinary(file, carpeta):
    resultado = cloudinary.uploader.upload(
        file,
        folder=carpeta,
        resource_type="image"
    )
    return resultado["secure_url"]


# 🔐 LOGIN
@app.route('/login', methods=['POST'])
def login():
    datos = request.json
    nombre = datos.get('nombre')
    password = datos.get('password')
    try:
        conn = conexion_mysql()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id_usuario, nombre_completo FROM usuarios WHERE nombre_completo = %s AND password = %s",
            (nombre, password)
        )
        usuario = cursor.fetchone()
        conn.close()
        if usuario:
            return jsonify({"status": "success", "id_usuario": usuario[0], "nombre": usuario[1]}), 200
        return jsonify({"status": "error", "message": "Credenciales incorrectas"}), 401
    except Exception as e:
        print("ERROR LOGIN: ", e)
        return jsonify({"status": "error", "message": str(e)}), 500

# 📝 REGISTRO GRUPAL
@app.route('/registrar_grupal', methods=['POST'])
def registrar_grupal():
    try:
        id_lider = request.form.get('id_lider')
        tipo = request.form.get('tipo_evento')
        integrantes = json.loads(request.form.get('integrantes'))
        lat = request.form.get('lat')
        lon = request.form.get('lon')

        foto_grupo = request.files.get('foto_grupal')
        foto_doc = request.files.get('foto_documento')

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        

        conn = conexion_mysql()
        cursor = conn.cursor()
        alerta_msg = None
        
        #se modifico aca
        if tipo == 'ENTRADA':  
            oc_ref = request.form.get('oc_referencia')
            if not oc_ref:
                return jsonify({"status": "error", "message": "Debe seleccionar un servicio (OC)"}), 400
        

            ahora = datetime.now().time()
            limite = datetime.strptime("08:15:00", "%H:%M:%S").time()
            estado = "TEMPRANO" if ahora <= limite else "TARDANZA"

            try:
                path_grupo = subir_a_cloudinary(foto_grupo, f"asistencias/entrada/grupo/{id_lider}")
                path_doc = subir_a_cloudinary( foto_doc, f"asistencias/entrada/documento/{id_lider}")
            except Exception as e:
                return jsonify({"status": "error", "message": f"Error al subir imágenes: {e}"}), 500
            
            print("INSERTAR ASISTENCIA: ", id_lider, tipo, lat, lon, path_grupo, path_doc, estado, oc_ref, "Integrantes:", integrantes)

            try:

                cursor.execute("""
                    INSERT INTO asistencias
                    (id_lider, tipo_registro, fecha, hora, latitud, longitud,
                    foto_grupal_path, foto_documento_path, estado_asistencia, oc_referencia)
                    VALUES (%s, 'ENTRADA', CURDATE(), CURTIME(), %s, %s, %s, %s, %s, %s)
                """, (id_lider, lat, lon, path_grupo, path_doc, estado, oc_ref))

            
                id_asistencia = cursor.lastrowid

                for p in integrantes:
                    cursor.execute("""
                        INSERT INTO detalle_asistencia
                        (id_asistencia, nombre_integrante, dni, cargo)
                        VALUES (%s, %s, %s, %s)
                    """, (id_asistencia, p['nombre'], p['dni'], p['cargo']))

            except mysql.connector.Error as e:
                print("ERROR: MYSQL", e)
                conn.rollback()
                conn.close()
                return jsonify({"status": "error", "message": f"Error en base de datos: {e}"}), 500
            

        else:  # SALIDA
            cursor.execute("""
                SELECT id_asistencia, hora
                FROM asistencias
                WHERE id_lider = %s AND fecha = CURDATE() AND tipo_registro = 'ENTRADA'
                ORDER BY hora DESC
                LIMIT 1
            """, (id_lider,))
            registro = cursor.fetchone()

            if not registro:
                return jsonify({"status": "error", "message": "No hay entrada registrada hoy"}), 400

            id_asist_ent = registro[0]
            cursor.execute("""
                select TIMESTAMPDIFF(MINUTE, CONCAT(fecha, ' ', hora), NOW()) / 60
                FROM asistencias
                WHERE id_asistencia = %s
            """, (id_asist_ent,))

            resultado_horas = cursor.fetchone()
            minutos_totales = resultado_horas[0] if resultado_horas else 0
            horas_totales = round(minutos_totales / 60, 2)
            horas_extras = max(0, horas_totales - 8)


            cursor.execute("SELECT dni, nombre_integrante FROM detalle_asistencia WHERE id_asistencia = %s", (id_asist_ent,))
            filas = cursor.fetchall()
            dict_ent = {r[0]: r[1] for r in filas}

            dnis_ent = set(dict_ent.keys())
            dnis_sal = set(p['dni'] for p in integrantes)
            dict_sal = {p['dni']: p['nombre'] for p in integrantes}

            mensajes = []
            if dnis_ent - dnis_sal:
                mensajes.append("Falta: " + ", ".join(dict_ent[d] for d in dnis_ent - dnis_sal))
            if dnis_sal - dnis_ent:
                mensajes.append("Nuevo: " + ", ".join(dict_sal[d] for d in dnis_sal - dnis_ent))

            alerta_msg = " | ".join(mensajes) if mensajes else None

            path_grupo_sal = None
            path_doc_sal = None

            if foto_grupo:
                path_grupo_sal = subir_a_cloudinary(
                    foto_grupo,
                    f"asistencias/salida/grupo/{id_lider}"
                )

            if foto_doc:
                path_doc_sal = subir_a_cloudinary(
                    foto_doc,
                    f"asistencias/salida/documento/{id_lider}"
                )

            cursor.execute("""
                UPDATE asistencias SET
                    hora_salida = CURTIME(),
                    foto_grupal_salida_path = %s,
                    foto_doc_salida_path = %s,
                    estado_salida = 'FINALIZADO',
                    horas_trabajadas = %s,
                    horas_extras = %s,
                    observacion_personal = %s,
                    integrantes_salida = %s
                        
                WHERE id_asistencia = %s
            """, (path_grupo_sal, path_doc_sal, horas_totales, horas_extras, alerta_msg,
                  json.dumps(integrantes), id_asist_ent))

        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "tipo": tipo, "alerta": alerta_msg}), 200

    except Exception as e:
        print("ERROR GENERAL REGISTRAR GRUPAL: ", e)
        return jsonify({"error": str(e)}), 500
    
import pandas as pd
from flask import send_file
from io import BytesIO

# 📊 ADMIN 
@app.route('/admin/get_all', methods=['GET'])
def get_all_reports():
    try:
        conn = conexion_mysql()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT A.fecha, U.nombre_completo, A.hora, A.hora_salida,
                   A.estado_asistencia, A.estado_salida,
                   A.foto_grupal_path, A.foto_documento_path,
                   A.foto_grupal_salida_path, A.foto_doc_salida_path,
                   A.horas_trabajadas, A.observacion_personal,
                   A.id_asistencia, A.integrantes_salida,
                   A.latitud, A.longitud, A.oc_referencia,
                   S.cliente, S.descripcion,
                   A.observacion_admin,
                   A.horas_extras
                       
            FROM asistencias A
            JOIN usuarios U ON A.id_lider = U.id_usuario
            LEFT JOIN servicios S ON A.oc_referencia = S.oc
            WHERE A.tipo_registro = 'ENTRADA'
            ORDER BY A.fecha DESC, A.hora DESC
        """)
        rows = cursor.fetchall()
        resultados = []

        for r in rows:
            cursor.execute(
                "SELECT nombre_integrante, dni, cargo FROM detalle_asistencia WHERE id_asistencia = %s",
                (r['id_asistencia'],)
            )
            detalles = cursor.fetchall()

            integrantes_ent = [{"nombre": d['nombre_integrante'], "dni": d['dni'], "cargo": d['cargo']} for d in detalles]

            integrantes_sal = json.loads(r['integrantes_salida']) if r['integrantes_salida'] else []

            resultados.append({
                "fecha": str(r['fecha']),
                "nombre_jefe": r['nombre_completo'],

                "servicio": {
                    "oc": r['oc_referencia'],
                    "cliente": r['cliente'],
                    "descripcion": r['descripcion']
                },
                "entrada": {
                    "hora": str(r['hora']),
                    "estado": r['estado_asistencia'],
                    "fotos": [r['foto_grupal_path'], r['foto_documento_path']],
                    "integrantes": integrantes_ent,
                    "ubicacion": {"lat": r['latitud'], "lon": r['longitud']}
                },
                "salida": {
                    "hora": str(r['hora_salida']) if r['hora_salida'] else None,
                    "fotos": [r['foto_grupal_salida_path'], r['foto_doc_salida_path']],
                    "alerta": r['observacion_personal'],
                    "integrantes": integrantes_sal
                },
                "horas_totales": r['horas_trabajadas'],
                "horas_extras": r['horas_extras'],
                "observacion_admin": r['observacion_admin'] or "",
                "id_asistencia":int(r['id_asistencia']) if r['id_asistencia'] is not None else None

            })

        conn.close()
        return jsonify(resultados), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/guardar_observacion', methods=['POST'])
def guardar_observacion_admin():
    try:
        data = request.json
        id_asistencia = data.get('id_asistencia')
        observacion = data.get('observacion_admin')

        if id_asistencia is None:
            return jsonify({"status": "error", "message": "ID inválido"}), 400

        conn = conexion_mysql()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE asistencias
            SET observacion_admin = %s
            WHERE id_asistencia = %s
        """, (observacion, id_asistencia))

        conn.commit()
        conn.close()

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    
# 🔎 BUSCAR SERVICIOS (TYPEAHEAD)
@app.route('/servicios/buscar', methods=['GET'])
def buscar_servicios():
    try:
        q = request.args.get('q', '').strip()

        if len(q) < 2:
            return jsonify([])

        conn = conexion_mysql()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT oc, cliente, descripcion
            FROM servicios
            WHERE oc LIKE %s
            ORDER BY oc
            LIMIT 10
        """, (f"%{q}%",))

        resultados = cursor.fetchall()
        conn.close()

        return jsonify(resultados), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/admin/export_excel', methods=['GET'])
def exportar_excel_por_oc():
    try:
        oc = request.args.get('oc')

        if not oc:
            return jsonify({"error": "OC requerida"}), 400

        conn = conexion_mysql()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                A.fecha,
                U.nombre_completo AS jefe_grupo,
                A.oc_referencia,
                S.cliente,
                S.descripcion AS servicio,
                       
                    GROUP_CONCAT(
                       
                        CONCAT(D.nombre_integrante, ' (', D.cargo, ')')
                        SEPARATOR ' | '
                    ) AS integrantes,

                A.estado_asistencia,        
                A.hora,
                A.hora_salida,
                A.horas_trabajadas,
                A.horas_extras,
                A.estado_salida,
                A.observacion_personal,
                A.observacion_admin,
                A.latitud,
                A.longitud,
                       
                A.foto_grupal_path,
                A.foto_documento_path,
                A.foto_grupal_salida_path,
                A.foto_doc_salida_path
                       
            FROM asistencias A
            JOIN usuarios U ON A.id_lider = U.id_usuario
            LEFT JOIN servicios S ON A.oc_referencia = S.oc
            LEFT JOIN detalle_asistencia D ON A.id_asistencia = D.id_asistencia
                       
            WHERE A.oc_referencia = %s
              AND A.tipo_registro = 'ENTRADA'
            
            GROUP BY A.id_asistencia
            ORDER BY A.fecha, A.hora
        """, (oc,))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return jsonify({"error": "No hay datos para este OC"}), 404

        df = pd.DataFrame(rows)

        df['ubicacion'] = df.apply(
            lambda r: f"https://www.google.com/maps?q={r['latitud']},{r['longitud']}"
            if pd.notna(r['latitud']) and pd.notna(r['longitud']) else '',
            axis=1
        )
        df.drop(columns=['latitud','longitud'], inplace = True)

        # ---- FORMATEAR HORA Y HORA_SALIDA (SIN "0 days") ----
        def formatear_hora(valor):
           if pd.isna(valor):
                return ''
           td = pd.to_timedelta(valor)
           h = int(td.components.hours)
           m = int(td.components.minutes)
           s = int(td.components.seconds)
           return f"{h:02d}:{m:02d}:{s:02d}"

        df['hora'] = df['hora'].apply(formatear_hora)
        df['hora_salida'] = df['hora_salida'].apply(formatear_hora)



        def horas_a_texto(h):
            if h is None:
                return ''
            h = float(h)
            horas = int(h)
            minutos = round((h - horas) * 60)
            return f"{horas} h {minutos} min"
        
        df['horas_trabajadas'] = df['horas_trabajadas'].apply(horas_a_texto)
        df['horas_extras'] = df['horas_extras'].apply(horas_a_texto)

        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Asistencias')

            ws = writer.book['Asistencias']

            ws.column_dimensions['A'].width = 12   # Fecha
            ws.column_dimensions['B'].width = 22   
            ws.column_dimensions['C'].width = 14   
            ws.column_dimensions['D'].width = 20   
            ws.column_dimensions['E'].width = 100  
            ws.column_dimensions['F'].width = 100  
            ws.column_dimensions['G'].width = 16   
            ws.column_dimensions['H'].width = 12   
            ws.column_dimensions['I'].width = 12  
            ws.column_dimensions['J'].width = 18   
            ws.column_dimensions['K'].width = 16   
            ws.column_dimensions['L'].width = 16   
            ws.column_dimensions['M'].width = 70   
            ws.column_dimensions['N'].width = 120   
            ws.column_dimensions['O'].width = 110  
            ws.column_dimensions['P'].width = 110   
            ws.column_dimensions['Q'].width = 110   
            ws.column_dimensions['R'].width = 110
            ws.column_dimensions['S'].width = 70
            


        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name=f"reporte_asistencia_OC_{oc}.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/sync_servicios', methods=['POST'])
def sync_servicios():
    try:
        FILE_ID = os.getenv("SERVICIOS_SHEET_ID")
        if not FILE_ID:
            return jsonify({"error": "SERVICIOS_SHEET_ID no definido"}), 500

        url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"

        print("Descargando Excel desde Google Drive...")
        response = requests.get(url)
        response.raise_for_status()

        df = pd.read_excel(io.BytesIO(response.content), engine='openpyxl')

        # Limpieza de cabeceras
        if 'Unnamed: 0' in df.columns or df.columns[0] is None:
            df.columns = df.iloc[0]
            df = df[1:]

        df.columns = [str(c).strip().upper() for c in df.columns]
        print("Columnas:", df.columns.tolist())

        conn = conexion_mysql()
        cursor = conn.cursor()

        # Limpiar tabla
        cursor.execute("TRUNCATE TABLE servicios")

        count = 0
        for _, row in df.iterrows():
            oc = str(row.get('OC', '')).strip()
            cliente = str(row.get('CLIENTE', '')).strip()

            descripcion = row.get('DESCRIPCIÓN')
            if descripcion is None:
                descripcion = row.get('DESCRIPCION', '')
            descripcion = str(descripcion).strip()

            if oc and oc.lower() != 'nan':
                cursor.execute("""
                    INSERT INTO servicios (oc, cliente, descripcion)
                    VALUES (%s, %s, %s)
                """, (oc, cliente, descripcion))
                count += 1

        conn.commit()
        conn.close()

        return jsonify({
            "status": "ok",
            "registros": count
        })

    except Exception as e:
        print("ERROR SYNC:", e)
        return jsonify({"error": str(e)}), 500
    

@app.route('/admin/login', methods=['POST'])
def login_admin():
    data = request.json
    usuario = data.get('usuario')
    password = data.get('password')

    conn = conexion_mysql()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT id
        FROM admin_usuarios
        WHERE usuario = %s AND password = %s
    """, (usuario, password))

    admin = cursor.fetchone()
    conn.close()

    if admin:
        return jsonify({"status": "ok"}), 200
    else:
        return jsonify({"status": "error"}), 401




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
