def save_last_message(redis_client, user_id, mensagem):
    redis_client.set(f"user:{user_id}:ultima", mensagem)

def get_last_message(redis_client, user_id):
    return redis_client.get(f"user:{user_id}:ultima")
