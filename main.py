# main.py
from flask import Flask, request, abort # Adicione Flask, request, abort
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup # Remova Updater aqui se já estiver importado
from telegram.ext import ( # Mantenha estas importações
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
)
import os
import logging
from dotenv import load_dotenv
import google.generativeai as genai
import json # Garanta que json esteja importado se você usa ele para carregar os dados
import redis_handler # Importe sua lógica de Redis
import faq_handler # Importe seu faq_handler

# Configure o logger
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente do .env (para desenvolvimento local)
load_dotenv()

# Variáveis de ambiente
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") # Verifique se esta variável é TELEGRAM_BOT_TOKEN ou TELEGRAM_TOKEN
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REDIS_URL = os.getenv("REDIS_URL")

# Inicialização do Redis
if REDIS_URL:
    redis_client = redis_handler.init_redis(REDIS_URL) # A função init_redis precisa ser adaptada em redis_handler.py para aceitar REDIS_URL
    logger.info("Redis configurado.")
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
with open('data/apresentacao.json', 'r', encoding='utf-8') as f:
    apresentacao_data = json.load(f)['1']
with open('data/faq.json', 'r', encoding='utf-8') as f:
    faq_data = json.load(f)

# Crie uma instância do Flask e atribua-a à variável 'app'
app = Flask(__name__) # <--- ESSA LINHA FOI ADICIONADA/CORRIGIDA AQUI

# Inicializa o Updater (para webhook) - movemos para o escopo global ou para uma função de inicialização
# As handlers precisam ser definidas no dispatcher globalmente ou na função de setup do bot
updater = Updater(TOKEN, use_context=True)
dispatcher = updater.dispatcher

# Funções do bot (start, button, mensagem) - mantenha-as como estão, mas certifique-se de que usem redis_client e model
# (O código abaixo é um exemplo simplificado, mantenha suas implementações completas)

# /start
def start(update: Update, context):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("📍 Onde fica?", callback_data='local')],
        [InlineKeyboardButton("🕒 Horário", callback_data='horario')],
        [InlineKeyboardButton("🍻 Quantos litros?", callback_data='litros')],
        [InlineKeyboardButton("📋 Cardápio", callback_data='cardapio')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(apresentacao_data['resposta'], reply_markup=reply_markup)
    if redis_client:
        redis_handler.save_last_message(redis_client, user_id, "boas-vindas") # Mudamos para "boas-vindas" para ser mais descritivo


# Botão clicado
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
        query.edit_message_text(text="Para ver nosso cardápio completo, acesse: [Link para o Cardápio]") # Substitua pelo link real
    if redis_client:
        redis_handler.save_last_message(redis_client, user_id, f"botão_{data}")

# Mensagens de texto
def mensagem(update: Update, context):
    user_id = update.effective_user.id
    texto = update.message.text.lower().strip()
    ultima = redis_handler.get_last_message(redis_client, user_id) if redis_client else "" # Verificação de redis_client

    resposta_faq, sugestoes_faq = faq_handler.responder_ou_sugerir(texto)

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
            # Fallback se a API Gemini falhar ou não estiver configurada
            pass

    # Fallback com sugestões via botão (se não houver resposta FAQ ou Gemini)
    keyboard = [
        [InlineKeyboardButton("📍 Onde fica?", callback_data='local')],
        [InlineKeyboardButton("🕒 Horário", callback_data='horario')],
        [InlineKeyboardButton("🍻 Quantos litros?", callback_data='litros')]
    ]
    # Adiciona o botão de cardápio se não for uma resposta de cardápio
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
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, mensagem))


# O endpoint para o webhook do Telegram
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), updater.bot)
    dispatcher.process_update(update)
    return "ok"

# Função principal para execução local (para testar em sua máquina)
if __name__ == "__main__":
    # Para desenvolvimento local, você pode usar polling ou um servidor Flask local
    # Para deploy no Render, o Gunicorn usa a rota @app.route
    # updater.start_polling()
    # updater.idle()
    app.run(port=int(os.environ.get("PORT", 5000))) # Só para testar localmente, o Gunicorn no Render cuidará disso