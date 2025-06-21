from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import face_recognition
import numpy as np
import cv2
import shutil
from pathlib import Path
from typing import List

app = FastAPI()

# Liberar acesso CORS para o frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ou ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pasta com rostos cadastrados
PASTA_ROSTOS = Path("known_faces")
banco_embeddings = []

# Pré-carregamento dos vetores dos rostos cadastrados
def carregar_rostos_conhecidos():
    for imagem_path in PASTA_ROSTOS.glob("*.jpeg"):
        imagem = face_recognition.load_image_file(imagem_path)
        encoding = face_recognition.face_encodings(imagem)
        if encoding:
            banco_embeddings.append((imagem_path.stem, encoding[0]))
        else:
            print(f"Nenhum rosto encontrado em {imagem_path.name}")

carregar_rostos_conhecidos()


@app.post("/face")
async def reconhecer_rosto(imagem: UploadFile = File(...)):
    # Salvar temporariamente o arquivo
    caminho_temp = Path("temp.jpg")
    with caminho_temp.open("wb") as buffer:
        shutil.copyfileobj(imagem.file, buffer)

    # Abrir com OpenCV para conversão em escala de cinza e redimensionamento
    imagem_cv = cv2.imread(str(caminho_temp))
    imagem_cv = cv2.resize(imagem_cv, (400, 400))
    imagem_gray = cv2.cvtColor(imagem_cv, cv2.COLOR_BGR2GRAY)

    # Recarregar a imagem com face_recognition (em RGB)
    imagem_rgb = cv2.cvtColor(imagem_cv, cv2.COLOR_BGR2RGB)
    locais_dos_rostos = face_recognition.face_locations(imagem_rgb)
    embeddings = face_recognition.face_encodings(imagem_rgb, locais_dos_rostos)

    resultados = []

    for emb in embeddings:
        nome_match = "Desconhecido"
        menor_distancia = 0.6  # threshold

        for nome_ref, emb_ref in banco_embeddings:
            distancia = np.linalg.norm(emb - emb_ref)
            if distancia < menor_distancia:
                nome_match = nome_ref
                menor_distancia = distancia

        resultados.append({"nome": nome_match, "distancia": round(float(menor_distancia), 4)})

    return {"qtd_rostos_detectados": len(embeddings), "resultados": resultados}
