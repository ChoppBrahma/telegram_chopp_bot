import os
import asyncio
from http import HTTPStatus
from flask import Flask, request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, # Usando a nova classe Application
    ContextTypes,
    MessageHandler,
    filters, # <--- ESSA LINHA PRECISA ESTAR COM 'filters' minúsculo
    CallbackQueryHandler,
    CommandHandler
)
import json # Importação necessária para ler arquivos JSON

# --- Configuração ---
TOKEN = os.environ.get("BOT_TOKEN") # <--- Variável de ambiente deve ser BOT_TOKEN
PORT = int(os.environ.get("PORT", 8000)) # Porta para o servidor web

# --- Carregar dados de FAQ ---
# O bot.py que você enviou antes não tinha apresentação_data, então mantive apenas o FAQ.
# Se precisar de apresentação_data, adicione um carregamento similar aqui.
try:
    with open('data/faq.json', 'r', encoding='utf-8') as f:
        faq_data = json.load(f)
    print("FAQ carregado com sucesso de data/faq.json.")
except FileNotFoundError:
    print("Erro: 'data/faq.json' não encontrado. Certifique-se de que o arquivo existe na pasta 'data'.")
    faq_data = [] # Inicializa vazio para evitar erros, mas o bot não terá FAQs
except json.JSONDecodeError:
    print("Erro: 'data/faq.json' contém JSON inválido. Verifique a formatação.")
    faq_data = [] # Inicializa vazio

# --- Lista de Regiões Atendidas (do seu bot.py anterior) ---
REGIOES_ATENDIDAS = [
    "agua quente", "aguas claras", "arniqueira", "brazlandia", "ceilandia",
    "gama", "guara", "nucleo bandeirante", "park way", "recanto das emas",
    "riacho fundo", "riacho fundo ii", "samambaia", "santa maria",
    "scia/estrutural", "sia", "sol nascente / por do sol", "taguatinga",
    "valparaiso de goias", "vicente pires"
]

# --- Lógica do Bot (Handlers) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_start = (
        "Olá! Tudo bem? Aqui é da equipe do Chopp Brahma Express de Águas Claras. "
        "Passando pra te mostrar como ficou fácil garantir seu chopp gelado, com desconto especial, "
        "entregue direto na sua casa!\n\n"
        "Já pensou em garantir seu Chopp Brahma com até 20% OFF, sem sair de casa? É só clicar:\n"
        "https://www.choppbrahmaexpress.com.br/chopps\n"
        "ou\n"
        "https://www.ze.delivery/produtos/categoria/chopp\n\n"
        "Aliás, você sabe tirar o chopp perfeito? Dá uma olhada nesse link "
        "https://l1nk.dev/sabe-tirar-o-chopp-perfeito e descubra como deixar seu chope ainda melhor!"
    )
    await update.message.reply_text(texto_start)

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text.lower()
    texto_normalizado = texto_usuario.translate(str.maketrans({
        'á': 'a', 'â': 'a', 'ã': 'a',
        'é': 'e', 'ê': 'e',
        'í': 'i',
        'ó': 'o', 'ô': 'o',
        'ú': 'u',
        'ç': 'c'
    }))

    contem_palavra_de_regiao = any(p in texto_normalizado for p in ["atende", "entrega", "regiao", "bairro", "cidade"])
    regiao_encontrada = next((r for r in REGIOES_ATENDIDAS if r in texto_normalizado), None)

    if contem_palavra_de_regiao and regiao_encontrada:
        await update.message.reply_text(
            f"Sim, atendemos em {regiao_encontrada.title()}! ✅\n"
            "Pode fazer seu pedido pelo site que entregamos aí."
        )
        return

    scored_faqs = []
    palavras_do_usuario = set(texto_usuario.split())
    for item in faq_data:
        intersecao = palavras_do_usuario.intersection(set(item["palavras_chave"]))
        score = len(intersecao)
        if score > 0:
            scored_faqs.append({"faq": item, "score": score})

    scored_faqs.sort(key=lambda x: x["score"], reverse=True)

    if not scored_faqs:
        await update.message.reply_text(
            "Desculpe, não entendi. 🤔\n"
            "Você pode perguntar sobre horário, formas de pagamento, ou se atendemos em uma região específica."
        )
        return

    max_score = scored_faqs[0]["score"]
    top_matched_faqs = [s["faq"] for s in scored_faqs if s["score"] == max_score]

    if len(top_matched_faqs) == 1:
        await update.message.reply_text(top_matched_faqs[0]["resposta"])
    else:
        keyboard = [[InlineKeyboardButton(f["pergunta"], callback_data=f"faq_id_{f['id']}")] for f in top_matched_faqs]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Encontrei algumas informações que podem ser úteis. Qual delas você procura?",
            reply_markup=reply_markup
        )

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    if callback_data.startswith("faq_id_"):
        faq_id = int(callback_data[len("faq_id_"):])
        faq = next((item for item in faq_data if item["id"] == faq_id), None)
        if faq:
            await query.message.reply_text(text=faq["resposta"])
            await query.edit_message_reply_markup(reply_markup=None)
        else:
            await query.message.reply_text(text="Desculpe, não consegui encontrar a resposta para essa opção.")

# --- Configuração da Aplicação e Servidor ---
# Instância do Application (para o bot do Telegram)
ptb = Application.builder().token(TOKEN).build()
ptb.add_handler(CommandHandler("start", start_command))
ptb.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), responder)) # <--- Uso correto de filters
ptb.add_handler(CallbackQueryHandler(button_callback_handler))

# Instância do Flask (para o servidor web)
flask_app = Flask(__name__) # <--- A instância Flask é chamada 'flask_app'

# Função para processar updates de forma assíncrona
def process_update(update_data):
    try:
        update = Update.de_json(update_data, ptb.bot)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(ptb.process_update(update))
        loop.close()
    except Exception as e:
        print(f"Erro ao processar update: {e}")

# Rotas para o webhook do Telegram
@flask_app.route(f"/api/telegram/webhook", methods=["POST"])
def telegram_webhook():
    try:
        data = request.get_json(force=True)
        if data:
            process_update(data)
        return Response(status=HTTPStatus.OK)
    except Exception as e:
        print(f"Erro no webhook: {e}")
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

@flask_app.route("/webhook", methods=["POST"])
def telegram_webhook_legacy(): # Rota de compatibilidade, caso o webhook esteja apontado para /webhook
    try:
        data = request.get_json(force=True)
        if data:
            process_update(data)
        return Response(status=HTTPStatus.OK)
    except Exception as e:
        print(f"Erro no webhook: {e}")
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

@flask_app.route("/health", methods=["GET"])
def health_check():
    return "Bot is healthy and running!", HTTPStatus.OK

@flask_app.route("/webhook-info", methods=["GET"])
def webhook_info():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        webhook_info = loop.run_until_complete(ptb.bot.get_webhook_info())
        loop.close()
        return {
            "url": webhook_info.url,
            "has_custom_certificate": webhook_info.has_custom_certificate,
            "pending_update_count": webhook_info.pending_update_count,
            "max_connections": webhook_info.max_connections,
            "ip_address": webhook_info.ip_address
        }
    except Exception as e:
        return {"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR

def set_telegram_webhook():
    webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/api/telegram/webhook"
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(ptb.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES))
        loop.close()
        print(f"Webhook configurado para: {webhook_url}")
    except Exception as e:
        print(f"Erro ao configurar webhook: {e}")

if __name__ == "__main__":
    set_telegram_webhook() # Setar o webhook quando rodar localmente
    flask_app.run(host="0.0.0.0", port=PORT)