from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import face_recognition
import numpy as np
import cv2
import shutil
import mysql.connector
from datetime import datetime, timedelta
import pytz
import csv
from fpdf import FPDF
import serial  # Para comunicação com o Arduino
from pathlib import Path

app = FastAPI()

# Liberar acesso CORS para o frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # ou ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Conectar ao banco de dados MySQL
db = mysql.connector.connect(
    host="localhost",         
    user="root",              
    password="suaSenhaSegura",  
    database="reconhecimento_facial"  
)

cursor = db.cursor()

# Função para carregar os rostos e embeddings do banco de dados
def carregar_rostos_conhecidos():
    banco_embeddings = []
    cursor.execute("SELECT id, nome, embedding FROM usuarios")
    resultados = cursor.fetchall()

    for id_usuario, nome, embedding_bin in resultados:
        embedding = np.frombuffer(embedding_bin, dtype=np.float64)
        banco_embeddings.append((id_usuario, nome, embedding))
    
    return banco_embeddings

# Carregar os rostos conhecidos diretamente do banco de dados
banco_embeddings = carregar_rostos_conhecidos()

# Função para gerar o relatório semanal
def gerar_relatorio_semanal():
    cursor.execute("""
        SELECT nome, data_entrada, data_saida, tempo_total
        FROM registros_acesso
        INNER JOIN usuarios ON usuarios.id = registros_acesso.membro_id
        WHERE data_entrada BETWEEN CURDATE() - INTERVAL 7 DAY AND CURDATE()
    """)
    registros = cursor.fetchall()

    # Gerar CSV
    with open("relatorio_semanal.csv", "w", newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Nome', 'Data Entrada', 'Data Saída', 'Tempo Total (segundos)'])
        for registro in registros:
            writer.writerow(registro)

    # Gerar PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Relatório Semanal", ln=True, align='C')

    for registro in registros:
        pdf.cell(200, 10, txt=f"{registro[0]} - Entrada: {registro[1]} - Saída: {registro[2]} - Tempo Total: {registro[3]} seg", ln=True)
    
    pdf.output("relatorio_semanal.pdf")

# Função para gerar o relatório mensal
def gerar_relatorio_mensal():
    cursor.execute("""
        SELECT nome, data_entrada, data_saida, tempo_total
        FROM registros_acesso
        INNER JOIN usuarios ON usuarios.id = registros_acesso.membro_id
        WHERE data_entrada BETWEEN CURDATE() - INTERVAL 30 DAY AND CURDATE()
    """)
    registros = cursor.fetchall()

    # Gerar CSV
    with open("relatorio_mensal.csv", "w", newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Nome', 'Data Entrada', 'Data Saída', 'Tempo Total (segundos)'])
        for registro in registros:
            writer.writerow(registro)

    # Gerar PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Relatório Mensal", ln=True, align='C')

    for registro in registros:
        pdf.cell(200, 10, txt=f"{registro[0]} - Entrada: {registro[1]} - Saída: {registro[2]} - Tempo Total: {registro[3]} seg", ln=True)
    
    pdf.output("relatorio_mensal.pdf")

@app.post("/face")
async def reconhecer_rosto(imagem: UploadFile = File(...)):
    # Salvar temporariamente o arquivo
    caminho_temp = Path("temp.jpg")
    with caminho_temp.open("wb") as buffer:
        shutil.copyfileobj(imagem.file, buffer)

    # Abrir com OpenCV para conversão em escala de cinza e redimensionamento
    imagem_cv = cv2.imread(str(caminho_temp))
    imagem_cv = cv2.resize(imagem_cv, (400, 400))
    imagem_rgb = cv2.cvtColor(imagem_cv, cv2.COLOR_BGR2RGB)

    # Detectar rostos na imagem
    locais_dos_rostos = face_recognition.face_locations(imagem_rgb)
    embeddings = face_recognition.face_encodings(imagem_rgb, locais_dos_rostos)

    resultados = []

    for emb in embeddings:
        nome_match = "Desconhecido"
        menor_distancia = 0.6  # threshold
        membro_id = None

        for id_usuario, nome_ref, emb_ref in banco_embeddings:
            distancia = np.linalg.norm(emb - emb_ref)
            if distancia < menor_distancia:
                nome_match = nome_ref
                menor_distancia = distancia
                membro_id = id_usuario

        if nome_match != "Desconhecido":
            # Registrar a entrada no banco de dados
            data_entrada = datetime.now(pytz.timezone('America/Sao_Paulo'))
            cursor.execute("INSERT INTO registros_acesso (membro_id, data_entrada) VALUES (%s, %s)", (membro_id, data_entrada))
            db.commit()

            # Acionar o LED para entrada (comunicação com Arduino aqui)
            # Exemplo de comunicação serial com Arduino:
            arduino = serial.Serial('/dev/ttyACM0', 9600)
            arduino.write(b'entrada')  # Comando de entrada para o Arduino

            # Simular a saída após 5 minutos (300 segundos)
            data_saida = data_entrada + timedelta(seconds=20)  # 5 minutos depois
            cursor.execute("UPDATE registros_acesso SET data_saida = %s, tempo_total = TIMESTAMPDIFF(SECOND, data_entrada, %s) WHERE membro_id = %s AND data_saida IS NULL", 
                           (data_saida, data_saida, membro_id))
            db.commit()

            # Acionar o LED para saída (comunicação com Arduino aqui)
            arduino.write(b'saida')  # Comando de saída para o Arduino

        resultados.append({"nome": nome_match, "distancia": round(float(menor_distancia), 4)})

    return {"qtd_rostos_detectados": len(embeddings), "resultados": resultados}

@app.post("/saida")
async def registrar_saida(membro_id: int):
    # Registrar a saída no banco de dados
    data_saida = datetime.now(pytz.timezone('America/Sao_Paulo'))
    cursor.execute("UPDATE registros_acesso SET data_saida = %s, tempo_total = TIMESTAMPDIFF(SECOND, data_entrada, %s) WHERE membro_id = %s AND data_saida IS NULL", 
                   (data_saida, data_saida, membro_id))
    db.commit()

    # Acionar o LED para saída (comunicação com Arduino aqui)
    arduino = serial.Serial('/dev/ttyUSB0', 9600)
    arduino.write(b'saida')  # Comando de saída para o Arduino

    return {"status": "Saída registrada com sucesso!"}

# Fechar a conexão ao banco de dados ao final
@app.on_event("shutdown")
def shutdown_event():
    cursor.close()
    db.close()
