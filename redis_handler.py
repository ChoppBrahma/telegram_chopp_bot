# redis_handler.py
import redis
import os
from dotenv import load_dotenv
import urllib.parse # Adicione esta importação

# Carrega variáveis de ambiente (para desenvolvimento local)
load_dotenv()

def init_redis(redis_url):
    try:
        # Analisa a URL do Redis
        url = urllib.parse.urlparse(redis_url)
        return redis.StrictRedis(
            host=url.hostname,
            port=url.port,
            password=url.password,
            decode_responses=True
        )
    except Exception as e:
        # Isso vai logar o erro caso a URL seja inválida
        print(f"Erro ao inicializar Redis com URL: {e}")
        return None # Retorna None se a inicialização falhar

def save_last_message(redis_client, user_id, mensagem):
    if redis_client: # Adicione esta verificação
        redis_client.set(f"user:{user_id}:ultima", mensagem)

def get_last_message(redis_client, user_id):
    if redis_client: # Adicione esta verificação
        return redis_client.get(f"user:{user_id}:ultima")
    return None