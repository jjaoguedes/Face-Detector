from fastapi import FastAPI, UploadFile, File
import face_recognition
import numpy as np
import cv2
import shutil
import mysql.connector
from datetime import datetime
import pytz
import serial
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
import logging
import time

# Configuração de logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializa conexão serial com Arduino uma única vez
try:
    arduino = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
    time.sleep(2)  # Aguarda Arduino reiniciar
    logger.info("Conexão com Arduino estabelecida com sucesso.")
except serial.SerialException as e:
    logger.error(f"Erro ao conectar com o Arduino: {e}")
    arduino = None

def conectar_db():
    try:
        db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="facedetector123@",
            database="reconhecimento_facial"
        )
        logger.info("Conexão com o banco de dados realizada com sucesso!")
        return db
    except mysql.connector.Error as err:
        logger.error(f"Erro ao conectar ao banco de dados: {err}")
        return None

def carregar_rostos_conhecidos():
    banco_embeddings = []
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id, nome, embedding FROM usuarios")
        resultados = cursor.fetchall()
        for id_usuario, nome, embedding_bin in resultados:
            embedding = np.frombuffer(embedding_bin, dtype=np.float64)
            banco_embeddings.append((id_usuario, nome, embedding))
        logger.info("Embeddings carregados com sucesso.")
    except mysql.connector.Error as err:
        logger.error(f"Erro ao carregar embeddings: {err}")
    return banco_embeddings

db = conectar_db()
banco_embeddings = carregar_rostos_conhecidos()

@app.post("/face")
async def reconhecer_rosto(imagem: UploadFile = File(...)):
    try:
        caminho_temp = Path("temp.jpg")
        with caminho_temp.open("wb") as buffer:
            shutil.copyfileobj(imagem.file, buffer)

        imagem_cv = cv2.imread(str(caminho_temp))
        if imagem_cv is None:
            return {"erro": "Imagem inválida."}

        imagem_cv = cv2.resize(imagem_cv, (640, 480))
        imagem_rgb = cv2.cvtColor(imagem_cv, cv2.COLOR_BGR2RGB)

        locais_dos_rostos = face_recognition.face_locations(imagem_rgb)
        embeddings = face_recognition.face_encodings(imagem_rgb, locais_dos_rostos)

        if len(embeddings) == 0:
            return {"erro": "Nenhum rosto detectado."}

        for emb in embeddings:
            nome_match = "Desconhecido"
            membro_id = None
            menor_distancia = 0.6

            for id_usuario, nome_ref, emb_ref in banco_embeddings:
                dist = np.linalg.norm(emb - emb_ref)
                if dist < menor_distancia:
                    nome_match = nome_ref
                    membro_id = id_usuario
                    menor_distancia = dist

            if nome_match != "Desconhecido":
                try:
                    cursor = db.cursor()
                    cursor.execute("""
                        SELECT status, data_entrada FROM registros_acesso 
                        WHERE membro_id = %s ORDER BY data_entrada DESC LIMIT 1
                    """, (membro_id,))
                    registro = cursor.fetchone()
                    agora = datetime.now(pytz.timezone('America/Manaus'))

                    if not registro or registro[0] == 0:
                        cursor.execute("""
                            INSERT INTO registros_acesso (membro_id, data_entrada, status)
                            VALUES (%s, %s, 1)
                        """, (membro_id, agora))
                        db.commit()

                        if arduino and arduino.is_open:
                            arduino.write(b'e')
                            logger.info("Comando 'e' enviado ao Arduino (entrada).")

                        return {
                            "status": "entrada",
                            "membro_id": membro_id,
                            "nome": nome_match
                        }

                    elif registro[0] == 1:
                        data_entrada = registro[1]
                        if data_entrada.tzinfo is None:
                            data_entrada = data_entrada.replace(tzinfo=pytz.timezone('America/Manaus'))

                        tempo_total = (agora - data_entrada).total_seconds()
                        cursor.execute("""
                            UPDATE registros_acesso 
                            SET data_saida = %s, tempo_total = IFNULL(tempo_total, 0) + %s, status = 0
                            WHERE membro_id = %s AND data_saida IS NULL
                        """, (agora, tempo_total, membro_id))
                        db.commit()

                        if arduino and arduino.is_open:
                            arduino.write(b's')
                            logger.info("Comando 's' enviado ao Arduino (saída).")

                        return {
                            "status": "saida",
                            "membro_id": membro_id,
                            "nome": nome_match,
                            "tempo_total": round(tempo_total, 2)
                        }

                except mysql.connector.Error as err:
                    db.rollback()
                    logger.error(f"Erro de banco: {err}")
                    return {"erro": "Erro de banco de dados."}

        return {"erro": "Rosto não reconhecido."}

    except Exception as e:
        logger.error(f"Erro geral: {e}")
        return {"erro": "Erro ao processar a imagem ou realizar o reconhecimento."}

@app.on_event("shutdown")
def shutdown_event():
    if db and db.is_connected():
        db.close()
        logger.info("Conexão com o banco de dados encerrada.")
    if arduino and arduino.is_open:
        arduino.close()
        logger.info("Conexão com o Arduino encerrada.")
