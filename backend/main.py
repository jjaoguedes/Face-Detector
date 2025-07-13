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

# Configuração do logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Liberar acesso CORS para o frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Permite que o frontend no localhost:3000 acesse o backend
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos os métodos HTTP
    allow_headers=["*"],  # Permite todos os cabeçalhos
)

# Função para conectar ao banco de dados
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

# Função para carregar os rostos e embeddings do banco de dados
def carregar_rostos_conhecidos():
    banco_embeddings = []
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id, nome, embedding FROM usuarios")
        resultados = cursor.fetchall()

        for id_usuario, nome, embedding_bin in resultados:
            embedding = np.frombuffer(embedding_bin, dtype=np.float64)
            banco_embeddings.append((id_usuario, nome, embedding))
        
        logger.info("Rostos e embeddings carregados com sucesso do banco de dados.")
    except mysql.connector.Error as err:
        logger.error(f"Erro ao carregar os rostos do banco de dados: {err}")
    return banco_embeddings

# Carregar os rostos conhecidos diretamente do banco de dados
db = conectar_db()
if db:
    banco_embeddings = carregar_rostos_conhecidos()

@app.post("/face")
async def reconhecer_rosto(imagem: UploadFile = File(...)):
    try:
        # Salvar temporariamente o arquivo
        caminho_temp = Path("temp.jpg")
        with caminho_temp.open("wb") as buffer:
            shutil.copyfileobj(imagem.file, buffer)
        
        # Verificar se a imagem foi carregada corretamente
        imagem_cv = cv2.imread(str(caminho_temp))
        if imagem_cv is None:
            logger.error("Falha ao carregar a imagem com OpenCV.")
            return {"erro": "Falha ao carregar a imagem. Por favor, verifique o arquivo enviado."}
        imagem_cv = cv2.resize(imagem_cv, (640, 480))
        imagem_rgb = cv2.cvtColor(imagem_cv, cv2.COLOR_BGR2RGB)
        logger.info("Imagem carregada e convertida para RGB com sucesso.")

        # Detectar rostos na imagem
        locais_dos_rostos = face_recognition.face_locations(imagem_rgb)
        embeddings = face_recognition.face_encodings(imagem_rgb, locais_dos_rostos)

        if len(locais_dos_rostos) == 0:
            logger.warning("Nenhum rosto detectado na imagem.")
            return {"erro": "Nenhum rosto detectado na imagem."}

        logger.info(f"{len(locais_dos_rostos)} rostos detectados na imagem.")
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
                try:
                    # Verificar se o membro já tem um registro de entrada ou saída
                    cursor = db.cursor()
                    cursor.execute("""
                        SELECT status, data_entrada, data_saida FROM registros_acesso 
                        WHERE membro_id = %s ORDER BY data_entrada DESC LIMIT 1
                    """, (membro_id,))
                    registro_entrada = cursor.fetchone()

                    # Se não encontrar o registro de entrada ou se o membro já saiu (status = 0), cria-se um novo
                    if registro_entrada is None or registro_entrada[0] == 0:
                        logger.info(f"Membro ID {membro_id} não possui registro de entrada ativo ou saiu. Criando novo registro de entrada.")
                        
                        # Inserir o novo registro de entrada
                        data_entrada = datetime.now(pytz.timezone('America/Manaus'))  # Usando o horário atual para a entrada
                        cursor.execute("INSERT INTO registros_acesso (membro_id, data_entrada, status) VALUES (%s, %s, 1)", 
                                       (membro_id, data_entrada))
                        db.commit()

                        # Acionar o LED para entrada (comunicação com Arduino)
                        arduino = serial.Serial('/dev/ttyACM0', 9600)
                        arduino.write(b'entrada')  # Comando de entrada para o Arduino
                        logger.info(f"Entrada registrada para o membro ID: {membro_id}")
                        
                        # Retornar uma mensagem que a entrada foi registrada
                        return {"status": "Entrada registrada com sucesso."}
                    
                    # Garantir que a data_entrada seja offset-aware
                    if registro_entrada[1].tzinfo is None:
                        data_entrada = registro_entrada[1].replace(tzinfo=pytz.timezone('America/Manaus'))  # Adicionando o fuso horário à data de entrada
                    else:
                        data_entrada = registro_entrada[1]

                    # Garantir que a data_saida seja offset-aware
                    data_saida = datetime.now(pytz.timezone('America/Manaus'))
                    if data_saida.tzinfo is None:
                        data_saida = data_saida.replace(tzinfo=pytz.timezone('America/Manaus'))

                    # Verificar se o status é 0 (saiu) ou se não há registro
                    if not registro_entrada or registro_entrada[0] == 0:
                        # Registrar a entrada no banco de dados
                        cursor.execute("INSERT INTO registros_acesso (membro_id, data_entrada, status) VALUES (%s, %s, 1)", (membro_id, data_entrada))
                        db.commit()

                        # Acionar o LED para entrada (comunicação com Arduino)
                        arduino = serial.Serial('/dev/ttyACM0', 9600)
                        arduino.write(b'entrada')  # Comando de entrada para o Arduino
                        logger.info(f"Entrada registrada para o membro ID: {membro_id}")

                    elif registro_entrada[0] == 1:  # Se o status for 1 (entrou)
                        # Registrar a saída no banco de dados
                        tempo_total = (data_saida - data_entrada).total_seconds()  # Calculando o tempo de permanência

                        # Atualizar a saída e o tempo total no banco de dados
                        cursor.execute("""
                            UPDATE registros_acesso 
                            SET data_saida = %s, tempo_total = IFNULL(tempo_total, 0) + %s, status = 0
                            WHERE membro_id = %s AND data_saida IS NULL
                        """, (data_saida, tempo_total, membro_id))
                        db.commit()

                        # Acionar o LED para saída (comunicação com Arduino)
                        arduino = serial.Serial('/dev/ttyACM0', 9600)
                        arduino.write(b'saida')  # Comando de saída para o Arduino
                        logger.info(f"Saída registrada para o membro ID: {membro_id}")

                except mysql.connector.Error as err:
                    db.rollback()  # Rollback em caso de erro
                    logger.error(f"Erro ao registrar a entrada/saída no banco de dados: {err}")
                    return {"erro": f"Erro ao registrar a entrada/saída no banco de dados: {err}"}

                resultados.append({"nome": nome_match, "distancia": round(float(menor_distancia), 4)})

        return {"qtd_rostos_detectados": len(embeddings), "resultados": resultados}

    except Exception as e:
        logger.error(f"Erro ao processar imagem ou realizar reconhecimento: {e}")
        return {"erro": "Erro ao processar a imagem ou realizar o reconhecimento de rostos."}


    
@app.post("/saida")
async def registrar_saida(membro_id: int):
    # Registrar a saída no banco de dados
    data_saida = datetime.now(pytz.timezone('America/Manaus'))
    
    try:
        cursor = db.cursor()
        # Iniciar uma transação para maior segurança
        db.start_transaction()

        # Buscar a data de entrada para calcular o tempo total
        cursor.execute("""
            SELECT status, data_entrada, data_saida FROM registros_acesso 
            WHERE membro_id = %s AND data_saida IS NULL
        """, (membro_id,))
        registro_entrada = cursor.fetchone()
        
        if registro_entrada:
            data_entrada = registro_entrada[1]
            if data_entrada.tzinfo is None:
                data_entrada = data_entrada.replace(tzinfo=pytz.timezone('America/Manaus'))  # Garantir que seja offset-aware

            # Verifica se passou o tempo de permanência
            tempo_de_permanencia = (data_saida - data_entrada).total_seconds()
            
            if tempo_de_permanencia >= 3:
                # Atualizar o tempo total no banco de dados somando com o tempo de permanência anterior
                cursor.execute("""
                    UPDATE registros_acesso 
                    SET data_saida = %s, tempo_total = IFNULL(tempo_total, 0) + %s, status = 0
                    WHERE membro_id = %s AND data_saida IS NULL
                """, (data_saida, tempo_de_permanencia, membro_id))
                db.commit()

                # Acionar o LED para saída (comunicação com Arduino)
                arduino = serial.Serial('/dev/ttyACM0', 9600)
                arduino.write(b'saida')  # Comando de saída para o Arduino
                logger.info(f"Saída registrada com sucesso para o membro ID: {membro_id}")
                return {"status": "Saída registrada com sucesso!"}
            
        else:
            logger.warning(f"Entrada não registrada para o membro ID: {membro_id}. Impossível registrar saída.")
            return {"status": "Entrada não registrada, impossível registrar saída."}
    except mysql.connector.Error as err:
        db.rollback()  # Rollback em caso de erro
        logger.error(f"Erro ao registrar a saída no banco de dados: {err}")
        return {"status": "Erro ao registrar a saída."}

# Fechar a conexão ao banco de dados ao final
@app.on_event("shutdown")
def shutdown_event():
    cursor.close()
    db.close()
    logger.info("Conexão com o banco de dados encerrada com sucesso.")
