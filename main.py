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

# Configuração da API Bunny.net
STORAGE_API_KEY = os.environ.get("BUNNY_API_KEY")
STORAGE_ZONE_NAME = "contahistoria"
STORAGE_URL = f"https://storage.bunnycdn.com/{STORAGE_ZONE_NAME}"

if not STORAGE_API_KEY or not STORAGE_ZONE_NAME:
    raise ValueError("Configure as variáveis de ambiente BUNNY_API_KEY e STORAGE_ZONE_NAME.")

# Modelo para receber os dados no webhook
class StoryInput(BaseModel):
    id: str  # Identificador único da história
    text: str  # Texto da história


async def generate_audio_edgetts(text_chunks, output_path):
    """
    Gera áudio a partir de texto usando EdgeTTS.
    Combina múltiplos trechos em um único arquivo de áudio.
    """
    combined_audio = AudioSegment.empty()
    
    for idx, chunk in enumerate(text_chunks):
        temp_audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name

        # Usar EdgeTTS para gerar o áudio
        communicate = edge_tts.Communicate(chunk, "af-ZA-AdriNeural")  # Escolha da voz
        await communicate.save(temp_audio_path)

        # Carregar o áudio gerado
        audio_segment = AudioSegment.from_file(temp_audio_path, format="mp3")
        combined_audio += audio_segment

        # Remover o arquivo temporário
        os.unlink(temp_audio_path)

    # Exportar o áudio combinado
    combined_audio.export(output_path, format="mp3")


@app.post("/webhook")
async def process_story(data: StoryInput):
    """
    Processa a história recebida via webhook.
    """
    try:
        # Dividir o texto em trechos de até 3.000 caracteres
        text_chunks = [data.text[i:i+3000] for i in range(0, len(data.text), 3000)]

        # Caminho do arquivo final
        final_audio_path = f"{data.id}.mp3"

        # Gerar áudio com EdgeTTS
        await generate_audio_edgetts(text_chunks, final_audio_path)

        # Upload para Bunny.net
        upload_url = f"{STORAGE_URL}/{data.id}.mp3"
        with open(final_audio_path, "rb") as audio_file:
            headers = {"AccessKey": STORAGE_API_KEY}
            response = requests.put(upload_url, headers=headers, data=audio_file)

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
