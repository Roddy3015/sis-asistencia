#ESTE ARCHIVO SOLO FUNCIONA DE MANERA LOCAL :D

import pandas as pd
import mysql.connector
import requests
import io

def sync():
    FILE_ID = '1_awzgN1eqSRLkppKAU_xzeA3e8rne6QOsOjgQXIJRAE'
    url = f'https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx'

    print("--- INICIANDO PROCESO DE SINCRONIZACIÓN ---")

    try:
        # 1. Descargar Excel
        print("Descargando Excel desde Google Drive...")
        response = requests.get(url)
        response.raise_for_status()

        # 2. Leer Excel
        df = pd.read_excel(io.BytesIO(response.content), engine='openpyxl')

        # 3. Limpieza de cabeceras
        if 'Unnamed: 0' in df.columns or df.columns[0] is None:
            df.columns = df.iloc[0]
            df = df[1:]

        df.columns = [str(c).strip().upper() for c in df.columns]
        print(f"Columnas detectadas: {list(df.columns)}")

        # 4. Conexión MySQL
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Mega2026",
            database="sis_asistencia"
        )
        cursor = conn.cursor()

        # 5. Limpiar tabla
        print("Limpiando tabla 'Servicios'...")
        cursor.execute("TRUNCATE TABLE Servicios")

        # 6. Insertar datos
        print("Insertando registros...")
        count = 0

        for index, row in df.iterrows():
            oc = str(row.get('OC', '')).strip()
            cliente = str(row.get('CLIENTE', '')).strip()

            descripcion = row.get('DESCRIPCIÓN')
            if descripcion is None:
                descripcion = row.get('DESCRIPCION', '')
            descripcion = str(descripcion).strip()

            if oc and oc.lower() != 'nan' and oc != 'None':
                try:
                    cursor.execute("""
                        INSERT INTO Servicios (OC, Cliente, Descripcion)
                        VALUES (%s, %s, %s)
                    """, (oc, cliente, descripcion))
                    count += 1
                except Exception as e:
                    print(f"⚠️ Error fila {index} (OC: {oc}): {e}")

        conn.commit()
        conn.close()

        print(f"✅ ¡ÉXITO! {count} servicios sincronizados.")

    except Exception as e:
        print(f"❌ ERROR CRÍTICO: {e}")

if __name__ == "__main__":
    sync()
