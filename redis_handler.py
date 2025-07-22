import redis
import os
from dotenv import load_dotenv
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Carrega as variáveis de ambiente do .env se o ambiente for de desenvolvimento local.
# Em ambientes de produção como o Render, as variáveis já são injetadas diretamente no ambiente.
load_dotenv()

# Função para inicializar o cliente Redis.
# Esta função pode aceitar uma URL completa (comum em serviços de nuvem)
# ou construir a conexão a partir de host, porta e senha separados.
def init_redis(redis_url=None):
    try:
        if redis_url:
            # Se uma URL de Redis for fornecida (ex: redis://:password@host:port)
            # O 'decode_responses=True' garante que as strings retornadas não sejam bytes.
            return redis.from_url(redis_url, decode_responses=True)
        else:
            # Caso contrário, usa variáveis de ambiente separadas (útil para setups locais ou específicos)
            # Certifique-se de que REDIS_HOST, REDIS_PORT, REDIS_PASSWORD estão definidos.
            return redis.StrictRedis(
                host=os.getenv("REDIS_HOST"),
                port=int(os.getenv("REDIS_PORT")),
                password=os.getenv("REDIS_PASSWORD"),
                decode_responses=True
            )
    except Exception as e:
        logger.error(f"Erro ao inicializar conexão Redis: {e}", exc_info=True)
        return None # Retorna None se a inicialização falhar

# Função para salvar a última mensagem do usuário no Redis.
# 'redis_client' é a instância de conexão com o Redis.
def save_last_message(redis_client, user_id, mensagem):
    if redis_client: # Só tenta salvar se o cliente estiver inicializado
        try:
            redis_client.set(f"user:{user_id}:ultima", mensagem)
            logger.info(f"Mensagem salva no Redis para o usuário {user_id}.")
        except Exception as e:
            logger.error(f"Erro ao salvar mensagem no Redis para o usuário {user_id}: {e}", exc_info=True)
    else:
        logger.warning(f"Tentativa de salvar mensagem no Redis, mas o cliente não está inicializado para o usuário {user_id}.")

# Função para obter a última mensagem do usuário do Redis.
def get_last_message(redis_client, user_id):
    if redis_client: # Só tenta obter se o cliente estiver inicializado
        try:
            return redis_client.get(f"user:{user_id}:ultima")
        except Exception as e:
            logger.error(f"Erro ao obter última mensagem do Redis para o usuário {user_id}: {e}", exc_info=True)
            return None
    else:
        logger.warning(f"Tentativa de obter mensagem do Redis, mas o cliente não está inicializado para o usuário {user_id}.")
        return None

# O cliente Redis NÃO é inicializado diretamente neste arquivo.
# Ele será inicializado uma vez no main.py chamando init_redis().