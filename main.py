from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from pydub import AudioSegment
from io import BytesIO
import uvicorn
import os
import openai
from BunnyCDN.Storage import Storage  # Importação correta do Storage

# Inicializando o FastAPI
app = FastAPI()

# Configuração da API OpenAI
openai.api_key = os.environ.get("OPENAI_API_KEY")  # Substitua pela sua chave da OpenAI

# Configuração da API BunnyCDN
STORAGE_API_KEY = os.environ.get("BUNNY_API_KEY")  # Chave da API armazenada no Render
STORAGE_ZONE_NAME = "contahistoria"  # Nome da zona de armazenamento
STORAGE_ZONE_REGION = None  # Região da zona, opcional

# Inicializar o Storage do BunnyCDN
bunny_storage = Storage(STORAGE_API_KEY, STORAGE_ZONE_NAME, STORAGE_ZONE_REGION)

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

        # Fazer upload do arquivo para Bunny.net
        try:
            upload_path = f"{story_id}.mp3"
            bunny_storage.PutFile(file_name=upload_path, local_upload_file_path=final_audio_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao salvar no Bunny.net: {str(e)}")

        try:
            # Nome do arquivo dentro da zona de armazenamento
            upload_path = f"{story_id}.mp3"
            # Chamar o método PutFile com o caminho correto
            bunny_storage.PutFile(
                file_name=upload_path,  # Caminho do arquivo dentro do Bunny.net
                local_upload_file_path=final_audio_path  # Caminho do arquivo local
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao salvar no Bunny.net: {str(e)}")


        # Retornar sucesso
        return JSONResponse(status_code=200, content={"message": "Áudio gerado e salvo com sucesso"})

    except HTTPException as http_err:
        return JSONResponse(status_code=http_err.status_code, content={"error": http_err.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro desconhecido: {str(e)}"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Lê a variável PORT do ambiente ou usa 8000 como padrão
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
