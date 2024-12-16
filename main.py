from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from pydub import AudioSegment
from io import BytesIO
import uvicorn
import os
import openai
import requests
import tempfile
from pydub import AudioSegment
from BunnyCDN.Storage import Storage  # Importação correta do Storage

# Configuração do FastAPI
app = FastAPI()

# Configuração da API Bunny.net
STORAGE_API_KEY = os.environ.get("BUNNY_API_KEY")
STORAGE_ZONE_NAME = "contahistoria"
STORAGE_URL = f"https://storage.bunnycdn.com/{STORAGE_ZONE_NAME}"

if not STORAGE_API_KEY or not STORAGE_ZONE_NAME:
    raise ValueError("Configure as variáveis de ambiente BUNNY_API_KEY e STORAGE_ZONE_NAME.")

# Configuração da API OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("A variável de ambiente OPENAI_API_KEY não está configurada.")

# Inicializar cliente OpenAI
openai = OpenAI(api_key=OPENAI_API_KEY)

# Modelo para receber os dados no webhook
class StoryInput(BaseModel):
    id: str  # Identificador único da história
    text: str  # Texto da história


@app.post("/webhook")
async def process_story(data: StoryInput):
    """
    Processa a história recebida via webhook.
    """
    try:
        # Dividir o texto em trechos de até 3.000 caracteres
        text_chunks = [data.text[i:i+3000] for i in range(0, len(data.text), 3000)]

        # Criar arquivos de áudio para cada trecho
        audio_files = []
        for idx, chunk in enumerate(text_chunks):
            response = openai.audio.transcriptions.create(
                model="text-to-speech-1",  # Modelo da OpenAI para TTS
                text=chunk,
                output_format="mp3"
            )
            
            temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_audio.write(response)
            temp_audio.close()
            audio_files.append(temp_audio.name)

        # Combinar todos os arquivos de áudio em um único arquivo MP3
        final_audio_path = f"{data.id}.mp3"
        combined_audio = AudioSegment.empty()
        for audio_file in audio_files:
            audio_segment = AudioSegment.from_file(audio_file, format="mp3")
            combined_audio += audio_segment
            os.unlink(audio_file)  # Remover arquivos temporários

        combined_audio.export(final_audio_path, format="mp3")

        # Upload do arquivo final para Bunny.net
        upload_url = f"{STORAGE_URL}/{data.id}.mp3"
        with open(final_audio_path, "rb") as audio_file:
            headers = {"AccessKey": STORAGE_API_KEY}
            response = requests.put(upload_url, headers=headers, data=audio_file)

        # Verificar se o upload foi bem-sucedido
        if response.status_code == 201:
            # Remover o arquivo local após o upload
            os.unlink(final_audio_path)
            return {"message": "Áudio gerado e salvo com sucesso.", "id": data.id}
        else:
            raise HTTPException(status_code=response.status_code, detail=response.text)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar a história: {str(e)}")


# Rota raiz para verificação de status
@app.get("/")
def read_root():
    return {"message": "API está ativa e funcionando."}


# Configuração do servidor Uvicorn
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))  # Porta definida no ambiente ou 8000 como padrão
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

