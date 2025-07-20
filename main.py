import os
import json
import redis
from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from dotenv import load_dotenv

from redis_handler import save_last_message, get_last_message
from faq_handler import responder_ou_sugerir

# Carregar variáveis de ambiente
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")

# Inicializar Flask e Telegram
app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot=bot, update_queue=None, workers=4, use_context=True)

# Inicializar Redis
redis_client = redis.from_url(REDIS_URL)

# Carregar mensagem de apresentação
with open("data/apresentacao.json", encoding="utf-8") as f:
    apresentacao = json.load(f)["1"]["resposta"]

# Comando /start
def start(update, context):
    user_id = update.effective_user.id
    bot.send_message(chat_id=update.effective_chat.id, text=apresentacao)
    save_last_message(redis_client, user_id, "boas-vindas")

# Mensagem do usuário
def mensagem(update, context):
    user_id = update.effective_user.id
    texto = update.message.text
    resposta, sugestoes = responder_ou_sugerir(texto)

    if resposta:
        update.message.reply_text(resposta)
    if sugestoes:
        botoes = [[InlineKeyboardButton(p, callback_data=p)] for p in sugestoes]
        update.message.reply_text(
            "🔎 Não encontrei exatamente isso... Mas talvez você quisesse perguntar:",
            reply_markup=InlineKeyboardMarkup(botoes)
        )

    save_last_message(redis_client, user_id, texto)

# Clique em botão de sugestão
def callback(update, context):
    query = update.callback_query
    query.answer()
    resposta, _ = responder_ou_sugerir(query.data)
    query.message.reply_text(resposta)

# Configurar os handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, mensagem))
dispatcher.add_handler(CallbackQueryHandler(callback))

# Endpoint para Webhook do Telegram
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok", 200

# Endpoint de verificação
@app.route("/", methods=["GET"])
def index():
    return "✅ Bot CHOPP online com sucesso!", 200

# Webserver com porta visível ao Render
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
