from fastapi import FastAPI, UploadFile, File, Request
import face_recognition
import numpy as np
import cv2
import shutil
import mysql.connector
from datetime import datetime, timedelta
import pytz
import serial
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
import logging
import time
import pandas as pd
from io import BytesIO
from fastapi.responses import StreamingResponse

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
    time.sleep(2)
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

def registrar_falha(ip: str):
    agora = datetime.now(pytz.timezone('America/Manaus'))
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO falhas_reconhecimento (ip, timestamp, tentativas)
        VALUES (%s, %s, 1)
        ON DUPLICATE KEY UPDATE
            tentativas = tentativas + 1,
            timestamp = %s
    """, (ip, agora, agora))
    db.commit()

def verificar_bloqueio(ip: str):
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT tentativas, timestamp FROM falhas_reconhecimento WHERE ip = %s", (ip,))
    falha = cursor.fetchone()
    if falha and falha["tentativas"] >= 5:
        agora = datetime.now(pytz.timezone('America/Manaus'))
        timestamp = falha["timestamp"]

        # Adição para corrigir erro de datetime naive vs aware
        if timestamp.tzinfo is None:
            timestamp = pytz.timezone('America/Manaus').localize(timestamp)

        tempo_passado = agora - timestamp
        if tempo_passado < timedelta(minutes=5):
            return True
        else:
            cursor.execute("DELETE FROM falhas_reconhecimento WHERE ip = %s", (ip,))
            db.commit()
    return False

db = conectar_db()
banco_embeddings = carregar_rostos_conhecidos()

@app.post("/face")
async def reconhecer_rosto(request: Request, imagem: UploadFile = File(...)):
    ip = request.client.host
    if verificar_bloqueio(ip):
        return {"erro": "Muitas tentativas falhas. Tente novamente em alguns minutos."}

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
            registrar_falha(ip)
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
                            data_entrada = pytz.timezone('America/Manaus').localize(data_entrada)

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

        registrar_falha(ip)
        return {"erro": "Rosto não reconhecido."}

    except Exception as e:
        logger.error(f"Erro geral: {e}")
        return {"erro": "Erro ao processar a imagem ou realizar o reconhecimento."}

@app.get("/gerar-relatorio/semanal")
def gerar_relatorio_semanal():
    try:
        cursor = db.cursor(dictionary=True)
        agora = datetime.now(pytz.timezone('America/Manaus'))
        semana_passada = agora - timedelta(days=7)

        cursor.execute("""
            SELECT u.nome AS nome_membro, r.membro_id, r.data_entrada, r.data_saida, r.tempo_total
            FROM registros_acesso r
            JOIN usuarios u ON r.membro_id = u.id
            WHERE r.data_entrada >= %s
            ORDER BY u.nome ASC, r.data_entrada ASC
        """, (semana_passada,))
        registros = cursor.fetchall()

        if not registros:
            return {"erro": "Nenhum acesso registrado nos últimos 7 dias."}

        df = pd.DataFrame(registros)

        # Formatando datas e colunas
        df["Entrada"] = pd.to_datetime(df["data_entrada"]).dt.strftime('%d/%m/%Y %H:%M')
        df["Saída"] = pd.to_datetime(df["data_saida"]).dt.strftime('%d/%m/%Y %H:%M')
        df["Tempo Total (horas)"] = df["tempo_total"].apply(lambda x: round(x / 3600, 5) if x else 0)

        # Seleciona e renomeia colunas
        df_formatado = df[["nome_membro", "membro_id", "Entrada", "Saída", "Tempo Total (horas)"]]
        df_formatado.rename(columns={
            "nome_membro": "Nome do Membro",
            "membro_id": "ID do Membro"
        }, inplace=True)

        # Exporta para Excel
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_formatado.to_excel(writer, index=False, sheet_name='Acessos da Semana')

        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': 'attachment; filename=relatorio_semanal.xlsx'}
        )

    except Exception as e:
        logger.error(f"Erro ao gerar relatório semanal: {e}")
        return {"erro": "Erro ao gerar relatório semanal."}

@app.get("/gerar-relatorio/mensal")
def gerar_relatorio_mensal():
    try:
        cursor = db.cursor(dictionary=True)
        agora = datetime.now(pytz.timezone('America/Manaus'))
        inicio_mes = agora.replace(day=1)

        # Consulta: soma diária por membro
        cursor.execute("""
            SELECT u.nome AS nome_membro, r.membro_id, DATE(r.data_entrada) AS dia,
                   SUM(r.tempo_total) AS tempo_total_dia
            FROM registros_acesso r
            JOIN usuarios u ON r.membro_id = u.id
            WHERE r.data_entrada >= %s
            GROUP BY r.membro_id, dia
            ORDER BY u.nome ASC, dia ASC
        """, (inicio_mes,))
        dados_dia = cursor.fetchall()

        if not dados_dia:
            return {"erro": "Nenhum dado encontrado para o mês atual."}

        df_dia = pd.DataFrame(dados_dia)

        # Formata data e converte segundos para horas
        df_dia["Dia"] = pd.to_datetime(df_dia["dia"]).dt.strftime('%d/%m/%Y')
        df_dia["Tempo Total (horas)"] = df_dia["tempo_total_dia"].apply(lambda x: round(x / 3600, 5))

        # Reorganiza e renomeia colunas
        df_dia_formatado = df_dia[["nome_membro", "membro_id", "Dia", "Tempo Total (horas)"]]
        df_dia_formatado.rename(columns={
            "nome_membro": "Nome do Membro",
            "membro_id": "ID do Membro"
        }, inplace=True)

        # Cálculo do resumo estatístico mensal
        resumo = df_dia.groupby(["membro_id", "nome_membro"]).agg(
            Total_de_Horas_no_Mês=("tempo_total_dia", lambda x: round(x.sum() / 3600, 2)),
            Frequência_de_Dias=("dia", "nunique"),
            Média_Diária_de_Permanência=("tempo_total_dia", lambda x: round((x.sum() / x.nunique()) / 3600, 2))
        ).reset_index()

        resumo.rename(columns={
            "membro_id": "ID do Membro",
            "nome_membro": "Nome do Membro"
        }, inplace=True)

        # Geração do arquivo Excel
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_dia_formatado.to_excel(writer, index=False, sheet_name='Detalhado')
            resumo.to_excel(writer, index=False, sheet_name='Resumo_Estatístico')

        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': 'attachment; filename=relatorio_mensal.xlsx'}
        )

    except Exception as e:
        logger.error(f"Erro ao gerar relatório mensal: {e}")
        return {"erro": "Erro ao gerar relatório mensal."}

@app.on_event("shutdown")
def shutdown_event():
    if db and db.is_connected():
        db.close()
        logger.info("Conexão com o banco de dados encerrada.")
    if arduino and arduino.is_open:
        arduino.close()
        logger.info("Conexão com o Arduino encerrada.")
