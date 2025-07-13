import face_recognition
import mysql.connector
import numpy as np
from datetime import datetime
import pytz

# Função para conectar ao banco de dados
def conectar_db():
    db = mysql.connector.connect(
        host="localhost",  # ou o IP do servidor se estiver acessando remotamente
        user="root",    # ou 'root', dependendo do usuário que você criou
        password="facedetector123@",  # senha do usuário
        database="reconhecimento_facial"  # nome do banco de dados
    )
    return db

# Função para cadastrar rosto
def cadastrar_rosto(nome: str, imagem_path: str):
    # Carregar a imagem do rosto a partir do caminho
    imagem = face_recognition.load_image_file(imagem_path)
    
    # Detectar o rosto na imagem e obter o embedding
    embeddings = face_recognition.face_encodings(imagem)

    if len(embeddings) > 0:
        # Pega o primeiro rosto (caso haja mais de um, você pode escolher qual rosto usar)
        embedding = embeddings[0]
        
        # Verificar o tamanho do embedding para garantir que seja válido
        if len(embedding) != 128:
            return {"status": "O embedding gerado não é válido."}
        
        # Conectar ao banco de dados
        db = conectar_db()
        cursor = db.cursor()

        try:
            # Converte o embedding para formato binário
            embedding_bin = bytearray(embedding)

            # SQL para inserir o rosto no banco de dados
            query = "INSERT INTO usuarios (nome, embedding) VALUES (%s, %s)"
            values = (nome, embedding_bin)

            # Executar a query e salvar os dados no banco
            cursor.execute(query, values)
            db.commit()

            print(f"Rosto de {nome} cadastrado com sucesso!")

            return {"status": "Rosto cadastrado com sucesso!"}
        
        except mysql.connector.Error as err:
            # Caso ocorra algum erro no banco de dados, desfazer transações
            db.rollback()
            print(f"Erro ao salvar no banco de dados: {err}")
            return {"status": "Erro ao salvar o rosto no banco de dados."}
        
        finally:
            # Fechar a conexão com o banco de dados
            cursor.close()
            db.close()

    else:
        return {"status": "Nenhum rosto encontrado na imagem."}

# Exemplo de como usar manualmente:
if __name__ == "__main__":
    nome = "Joao"  # Nome do membro
    imagem_path = "/home/joaoguedes/Downloads/joao.jpeg"  # Caminho para a imagem que você deseja cadastrar

    resultado = cadastrar_rosto(nome, imagem_path)
    print(resultado)
