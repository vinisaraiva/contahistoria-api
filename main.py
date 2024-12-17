from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from pydub import AudioSegment
from io import BytesIO
import uvicorn
import os
import shutil
import asyncio
import edge_tts
import requests
import tempfile
from pydub import AudioSegment
from BunnyCDN.Storage import Storage  # Importação correta do Storage

# Configuração do FastAPI
app = FastAPI()

# Configuração da Bunny.net
STORAGE_API_KEY = os.environ.get("BUNNY_API_KEY")  # Chave de API do Bunny.net
STORAGE_ZONE_NAME = "storyme"  # Nome da zona de armazenamento
STORAGE_URL = f"https://storage.bunnycdn.com/{STORAGE_ZONE_NAME}"  # URL de upload

# Modelo de entrada
class StoryInput(BaseModel):
    id: str       # Identificador único da história
    text: str     # Texto da história
    gender: str   # Gênero da voz (male/female)
    language: str # Idioma (portuguese/english)

# Dicionário de vozes
VOICE_OPTIONS = {
    "portuguese": {
        "male": "pt-BR-AntonioNeural",
        "female": "pt-BR-FranciscaNeural"
    },
    "english": {
        "male": "en-US-GuyNeural",
        "female": "en-US-AriaNeural"
    }
}

# Função para selecionar a voz correta
def select_voice(language, gender):
    if language not in VOICE_OPTIONS or gender not in VOICE_OPTIONS[language]:
        raise ValueError("Idioma ou gênero inválido.")
    return VOICE_OPTIONS[language][gender]

# Função para gerar áudio com EdgeTTS
async def generate_audio_edgetts(text_chunks, voice, output_path):
    combined_audio = AudioSegment.empty()

    for idx, chunk in enumerate(text_chunks):
        # Gera o áudio temporário usando EdgeTTS
        temp_audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
        communicate = edge_tts.Communicate(chunk, voice)
        await communicate.save(temp_audio_path)

        # Combina os áudios
        audio_segment = AudioSegment.from_file(temp_audio_path, format="mp3")
        combined_audio += audio_segment

        # Remove o arquivo temporário
        os.unlink(temp_audio_path)

    # Exporta o áudio combinado
    combined_audio.export(output_path, format="mp3")

# Função para fazer upload do arquivo no Bunny.net
def upload_to_bunny(file_path, file_name):
    upload_url = f"{STORAGE_URL}/{file_name}"
    headers = {"AccessKey": STORAGE_API_KEY}

    with open(file_path, "rb") as file:
        response = requests.put(upload_url, headers=headers, data=file)

    if response.status_code == 201:
        return True
    else:
        raise HTTPException(status_code=response.status_code, detail=f"Erro ao enviar arquivo: {response.text}")

# Rota principal do webhook
@app.post("/webhook")
async def process_story(data: StoryInput):
    try:
        # Validação da voz e idioma
        voice = select_voice(data.language, data.gender)

        # Dividir o texto em trechos de até 3.000 caracteres
        text_chunks = [data.text[i:i + 3000] for i in range(0, len(data.text), 3000)]

        # Caminho temporário para o arquivo final
        final_audio_path = f"{data.id}.mp3"

        # Gerar áudio
        await generate_audio_edgetts(text_chunks, voice, final_audio_path)

        # Fazer upload do áudio gerado para Bunny.net
        upload_to_bunny(final_audio_path, f"{data.id}.mp3")

        # Remover o arquivo local após upload
        os.unlink(final_audio_path)

        # Resposta de sucesso
        return {"message": "Áudio gerado e salvo com sucesso.", "id": data.id}

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar a história: {str(e)}")

# Rota de teste
@app.get("/")
def read_root():
    return {"message": "API está ativa e funcionando."}

# Configuração do Uvicorn
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))  # Define a porta
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

