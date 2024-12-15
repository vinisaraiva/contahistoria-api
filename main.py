from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from pydub import AudioSegment
from io import BytesIO
import os
import openai
from bunnycdn.storage import BunnyCDNStorage

# Inicializando o FastAPI
app = FastAPI()

# Configuração da API OpenAI
openai.api_key = os.environ.get("openai_apikey")  # Substitua pela sua chave da OpenAI

# Configuração do Bunny.net
#BUNNY_API_KEY = "3c363c63-888a-4e06-b733-7ebf6cc368676d4ca3cf-d056-4d43-ab95-5b191d889b90"
BUNNY_API_KEY = os.environ.get("bunny_apikey")  # Sua API key do Bunny.net
STORAGE_ZONE = "contahistoria"
STORAGE_ZONE_ID = 849285
BUNNY_STORAGE_PATH = f"/{STORAGE_ZONE}/"

# Inicializando BunnyCDNStorage
bunny_storage = BunnyCDNStorage(
    api_key=BUNNY_API_KEY,
    storage_zone_name=STORAGE_ZONE
)

# Modelo de dados recebidos pela API
class StoryInput(BaseModel):
    id: str
    text: str

@app.post("/webhook")
async def process_story(story_input: StoryInput):
    try:
        # Extrair o texto e o ID do payload
        story_id = story_input.id
        story_text = story_input.text

        # Validar o tamanho do texto
        if len(story_text) <= 0:
            raise HTTPException(status_code=400, detail="Texto vazio recebido")

        # Dividir o texto em partes de no máximo 3.000 caracteres
        chunks = []
        max_chunk_size = 3000
        while len(story_text) > 0:
            chunks.append(story_text[:max_chunk_size])
            story_text = story_text[max_chunk_size:]

        # Transcrever cada parte para áudio usando a API OpenAI TTS
        audio_segments = []
        for idx, chunk in enumerate(chunks):
            try:
                response = openai.audio.speech.create(
                    model="tts-1",
                    voice="alloy",  # Altere conforme necessário
                    input=chunk
                )

                audio_content = response.content
                if not audio_content:
                    raise ValueError(f"Erro na transcrição do chunk {idx+1}")

                # Carregar o áudio em um formato manipulável (Pydub)
                audio = AudioSegment.from_file(BytesIO(audio_content), format="mp3")
                audio_segments.append(audio)

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Erro ao processar chunk {idx+1}: {str(e)}")

        # Unir todas as partes do áudio
        final_audio = sum(audio_segments)

        # Salvar o arquivo de áudio localmente
        final_audio_path = f"{story_id}.mp3"
        final_audio.export(final_audio_path, format="mp3")

        # Fazer upload do arquivo para Bunny.net usando a biblioteca BunnyCDN
        try:
            with open(final_audio_path, "rb") as file:
                bunny_storage.upload_file(f"{story_id}.mp3", file)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao salvar no Bunny.net: {str(e)}")

        # Retornar sucesso
        return JSONResponse(status_code=200, content={"message": "Áudio gerado e salvo com sucesso"})

    except HTTPException as http_err:
        return JSONResponse(status_code=http_err.status_code, content={"error": http_err.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro desconhecido: {str(e)}"})
