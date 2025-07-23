# main.py
from flask import Flask, request, abort
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters, # <--- CORRIGIDO: Agora é 'filters' (minúsculo)
)
import os
import logging
from dotenv import load_dotenv
import google.generativeai as genai
import json
import redis_handler
import faq_handler # Assegure-se de que faq_handler exista e esteja correto

# Configure o logger
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente
load_dotenv()

# Variáveis de ambiente
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REDIS_URL = os.getenv("REDIS_URL")

# Inicialização do Redis
if REDIS_URL:
    try:
        redis_client = redis_handler.init_redis(REDIS_URL)
        if redis_client:
            logger.info("Redis configurado com sucesso.")
        else:
            logger.warning("Erro ao inicializar Redis com REDIS_URL fornecido. Redis pode não funcionar.")
    except Exception as e:
        redis_client = None
        logger.error(f"Exceção ao inicializar Redis: {e}. As funcionalidades de Redis não funcionarão.")
else:
    redis_client = None
    logger.warning("REDIS_URL não configurado. As funcionalidades de Redis (salvar última mensagem) não funcionarão.")

# Inicialização do Gemini API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-pro")
    logger.info("API Gemini configurada.")
else:
    model = None
    logger.warning("GEMINI_API_KEY não configurado. As funcionalidades da API Gemini não funcionarão.")

# Carregar dados de apresentação e FAQ
try:
    with open('data/apresentacao.json', 'r', encoding='utf-8') as f:
        apresentacao_data = json.load(f)['1']
    with open('data/faq.json', 'r', encoding='utf-8') as f:
        faq_data = json.load(f)
except FileNotFoundError as e:
    logger.error(f"Erro ao carregar arquivos JSON: {e}. Verifique se 'data/apresentacao.json' e 'data/faq.json' existem.")
    apresentacao_data = {}
    faq_data = {}


# Crie uma instância do Flask e atribua-a à variável 'app' no escopo global
app = Flask(__name__)

# Inicializa o Updater (para webhook) - movemos para o escopo global
updater = Updater(TOKEN, use_context=True)
dispatcher = updater.dispatcher


# Funções do bot (start, button, mensagem) - certifique-se que estas funções estão definidas ANTES de serem usadas nos handlers
def start(update: Update, context):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("📍 Onde fica?", callback_data='local')],
        [InlineKeyboardButton("🕒 Horário", callback_data='horario')],
        [InlineKeyboardButton("🍻 Quantos litros?", callback_data='litros')],
        [InlineKeyboardButton("📋 Cardápio", callback_data='cardapio')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(apresentacao_data.get('resposta', 'Olá! Como posso ajudar?'), reply_markup=reply_markup)
    if redis_client:
        redis_handler.save_last_message(redis_client, user_id, "boas-vindas")


def button(update: Update, context):
    query = update.callback_query
    query.answer()
    user_id = query.effective_user.id
    data = query.data

    if data == 'local':
        query.edit_message_text(text="Estamos localizados na Rua das Cervejas, 123 - Centro, Cervejópolis.")
    elif data == 'horario':
        query.edit_message_text(text="Nosso horário de funcionamento é de Terça a Domingo, das 18h às 23h.")
    elif data == 'litros':
        query.edit_message_text(text="Oferecemos chopp em growlers de 1 Litro e 2 Litros. Também temos pacotes para eventos maiores!")
    elif data == 'cardapio':
        query.edit_message_text(text="Para ver nosso cardápio completo, acesse: [Link para o Cardápio]")
    if redis_client:
        redis_handler.save_last_message(redis_client, user_id, f"botão_{data}")

def mensagem(update: Update, context):
    user_id = update.effective_user.id
    texto = update.message.text.lower().strip()
    ultima = redis_handler.get_last_message(redis_client, user_id) if redis_client else ""

    # Usando o faq_handler corretamente
    resposta_faq = faq_handler.responder_faq(faq_data, texto) # Assumindo que faq_handler.responder_faq retorna string ou None

    if resposta_faq:
        update.message.reply_text(resposta_faq)
        if redis_client:
            redis_handler.save_last_message(redis_client, user_id, texto)
        return

    # Resposta com Gemini
    if model:
        try:
            response = model.generate_content(texto)
            update.message.reply_text(response.text)
            if redis_client:
                redis_handler.save_last_message(redis_client, user_id, texto)
            return
        except Exception as e:
            logger.error(f"Erro na API Gemini: {e}")
            pass # Continue para o fallback se a API Gemini falhar ou não estiver configurada

    # Fallback com sugestões via botão (se não houver resposta FAQ ou Gemini)
    keyboard = [
        [InlineKeyboardButton("📍 Onde fica?", callback_data='local')],
        [InlineKeyboardButton("🕒 Horário", callback_data='horario')],
        [InlineKeyboardButton("🍻 Quantos litros?", callback_data='litros')]
    ]
    if 'cardapio' not in texto and 'menu' not in texto:
        keyboard.append([InlineKeyboardButton("📋 Cardápio", callback_data='cardapio')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        f"🤔 Não entendi bem '{texto}'. Talvez você queira saber:",
        reply_markup=reply_markup
    )
    if redis_client:
        redis_handler.save_last_message(redis_client, user_id, texto)

# Adicione os handlers ao dispatcher
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CallbackQueryHandler(button))
dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem)) # <--- CORRIGIDO AQUI TAMBÉM


# O endpoint para o webhook do Telegram
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), updater.bot)
        dispatcher.process_update(update)
        return "ok"
    return abort(400) # Método não permitido


# Função para setar o webhook (chamada uma única vez, preferencialmente fora do deploy)
# ou pode ser chamada no final do main.py se quiser que seja setada a cada deploy
# MAS GERALMENTE É MELHOR SETAR MANULMENTE OU VIA UM SCRIPT SEPARADO
def set_webhook():
    if TOKEN and WEBHOOK_URL:
        webhook_url_with_token = f"{WEBHOOK_URL}/{TOKEN}"
        updater.bot.set_webhook(url=webhook_url_with_token)
        logger.info(f"Webhook configurado para: {webhook_url_with_token}")
    else:
        logger.warning("TOKEN ou WEBHOOK_URL não configurados. Não foi possível setar o webhook.")


# Isso só será executado quando você rodar `python main.py` localmente
# No Render, o Gunicorn executa `gunicorn main:app` e não entra neste bloco
if __name__ == "__main__":
    logger.info("Executando localmente. Configurarei o webhook e iniciarei o servidor Flask.")
    set_webhook() # Chame para setar o webhook quando rodar localmente
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000))) # Flask local para testar