import os
import json
import logging
from dotenv import load_dotenv

# Importações necessárias do python-telegram-bot v20+
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters # Note: filters em minúsculas
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update # Import Update para type hinting

# Importações dos módulos locais
import redis_handler
import faq_handler

# Importa a biblioteca do Google Gemini
import google.generativeai as genai

# Configuração de logging para acompanhar o que o bot está fazendo e erros.
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Obtenção das Variáveis de Ambiente ---
# É CRÍTICO que essas variáveis estejam configuradas no ambiente do Render.
load_dotenv() # Carrega .env para desenvolvimento local, não para Render
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Validação básica das variáveis de ambiente
if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN não configurado. O bot não poderá se conectar ao Telegram.")
    exit("TELEGRAM_TOKEN é obrigatório para iniciar o bot.")
if not REDIS_URL:
    logger.warning("REDIS_URL não configurado. As funcionalidades de Redis (salvar última mensagem) não funcionarão.")
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY não configurada. A funcionalidade de IA via Gemini pode não funcionar.")

# Inicializa o cliente Redis usando a função do redis_handler.
redis_client = None # Inicializa como None para controle
if REDIS_URL:
    try:
        redis_client = redis_handler.init_redis(REDIS_URL)
        if redis_client: # Verifica se a inicialização retornou um cliente válido
            # Teste de conexão Redis
            redis_client.ping()
            logger.info("Conexão Redis estabelecida com sucesso.")
        else:
            logger.error("redis_handler.init_redis retornou None. Conexão Redis falhou na inicialização.")
    except Exception as e:
        logger.error(f"Falha CRÍTICA ao conectar ao Redis na inicialização: {e}. As funcionalidades de Redis estarão desabilitadas.", exc_info=True)
        redis_client = None # Garante que redis_client seja None em caso de falha

# Configura a API do Google Gemini, se a chave estiver disponível.
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("API Gemini configurada.")
else:
    logger.warning("Variável de ambiente GEMINI_API_KEY não configurada. A funcionalidade de IA pode não funcionar.")

# --- Funções auxiliares para carregar dados JSON ---
def load_json_file(file_path, default_value=None):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Arquivo {file_path} não encontrado. Verifique o caminho.")
        return default_value if default_value is not None else {}
    except json.JSONDecodeError:
        logger.error(f"Erro ao decodificar JSON do arquivo {file_path}. Verifique o formato do arquivo.")
        return default_value if default_value is not None else {}

# Carrega os dados de apresentação
apresentacao_data = load_json_file('data/apresentacao.json', default_value={"introducao": {"texto": "Bem-vindo!"}, "opcoes": {}, "opcoes_respostas": {}})

# Dicionário global para armazenar sugestões temporariamente.
current_suggestions = {}

# --- Funções de Manipulação do Bot (agora todas 'async def') ---

async def start(update: Update, context):
    """Manipula o comando /start e exibe a mensagem de boas-vindas com opções."""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    if redis_client:
        redis_handler.save_last_message(redis_client, user_id, "/start")
    else:
        logger.warning(f"Redis indisponível para salvar última mensagem de /start para {user_id}.")
    logger.info(f"Usuário {user_id} ({user_name}) iniciou o bot com /start.")

    intro_message = apresentacao_data.get("introducao", {}).get("texto", "Olá! Como posso te ajudar hoje?")
    
    keyboard = []
    # Cria os botões com base nas opções definidas em apresentacao.json
    opcoes = apresentacao_data.get("opcoes", {})
    for button_text, callback_data in opcoes.items():
        # Validação: callback_data deve ter no máximo 64 bytes
        if len(callback_data.encode('utf-8')) > 64:
            logger.warning(f"Callback data muito longo para botão '{button_text}': '{callback_data}'. Será truncado para evitar erros.")
            callback_data = callback_data[:64] # Trunca o callback_data para 64 caracteres se for muito longo
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(intro_message, reply_markup=reply_markup)

async def button(update: Update, context):
    """Manipula cliques em botões inline."""
    query = update.callback_query
    await query.answer() # Responde à requisição do callback, importante para o Telegram.

    callback_data = query.data
    user_id = query.from_user.id

    if redis_client:
        redis_handler.save_last_message(redis_client, user_id, f"callback:{callback_data}")
    else:
        logger.warning(f"Redis indisponível para salvar callback para {user_id}.")
    logger.info(f"Usuário {user_id} clicou no botão com callback_data: {callback_data}")

    # Verifica se o callback_data é uma das respostas de apresentação
    opcoes_respostas = apresentacao_data.get("opcoes_respostas", {})
    if callback_data in opcoes_respostas:
        resposta = opcoes_respostas[callback_data]
        await query.edit_message_text(text=resposta) # Edita a mensagem original do botão
    elif callback_data.startswith("sug:"):
        # Se for um callback de sugestão gerado por `handle_message`
        suggested_text = current_suggestions.get(callback_data)
        if suggested_text:
            await query.edit_message_text(text=f"Você clicou em: \"{suggested_text}\". Por favor, digite essa pergunta para que eu possa te ajudar!")
        else:
            await query.edit_message_text(text="Desculpe, a sugestão clicada não foi encontrada ou expirou.")
    else:
        # Se não for uma opção de apresentação nem sugestão, tenta procurar no FAQ diretamente
        resposta_faq_callback, _ = faq_handler.responder_ou_sugerir(callback_data)
        if resposta_faq_callback:
            await query.edit_message_text(text=resposta_faq_callback)
        else:
            await query.edit_message_text(text=f"Desculpe, não encontrei informações para '{callback_data}'.")

async def call_ai_api(update: Update, context, prompt):
    """Função para chamar a API do Google Gemini para respostas inteligentes."""
    if not GEMINI_API_KEY:
        await update.message.reply_text("Desculpe, a funcionalidade de IA não está disponível no momento (chave de API não configurada).")
        return

    try:
        model = genai.GenerativeModel('gemini-pro')
        logger.info(f"Chamando Gemini com prompt: {prompt}")
        
        # Usa generate_content_async para não bloquear o loop de eventos do Telegram.
        response = await model.generate_content_async(prompt)

        ai_resposta = ""
        # Tenta extrair o texto da resposta, lidando com possíveis bloqueios de segurança do Gemini.
        if response and response.parts:
            try:
                ai_resposta = response.parts[0].text
            except IndexError:
                ai_resposta = "Não foi possível extrair a resposta da IA. Pode haver um problema com o conteúdo gerado (potencialmente inseguro)."
            except Exception as e:
                ai_resposta = f"Ocorreu um erro inesperado ao processar a resposta da IA: {e}"
        elif response and hasattr(response, 'text'): # Em alguns casos, a resposta pode vir diretamente em .text
            ai_resposta = response.text
        else:
            ai_resposta = "Desculpe, a IA não conseguiu gerar uma resposta clara. Poderia reformular?"
            
        # Adiciona um disclaimer para a resposta da IA, conforme solicitado.
        ai_resposta += "\n\n(Resposta gerada por IA, pode não ser 100% precisa.)"

        await update.message.reply_text(ai_resposta)

    except Exception as e:
        logger.error(f"Erro ao chamar a API Gemini: {e}", exc_info=True)
        await update.message.reply_text("Desculpe, estou com dificuldades técnicas para processar sua pergunta via IA agora. Tente novamente mais tarde.")

async def handle_message(update: Update, context):
    """Manipula todas as mensagens de texto que não são comandos."""
    user_id = update.effective_user.id
    mensagem_original = update.message.text
    mensagem_processada = mensagem_original.lower().strip() # Usado para salvar no Redis e para lógica interna

    if redis_client:
        redis_handler.save_last_message(redis_client, user_id, mensagem_processada)
    else:
        logger.warning(f"Redis indisponível para salvar mensagem para {user_id}.")
    logger.info(f"Mensagem recebida de {user_id}: {mensagem_original}")

    # Tenta obter uma resposta direta ou sugestões do faq_handler.
    # O faq_handler agora lida com saudações e termos genéricos como "chopp".
    resposta_faq, sugestoes_faq = faq_handler.responder_ou_sugerir(mensagem_original)

    if resposta_faq:
        # Se o FAQ encontrou uma resposta direta, envia-a.
        await update.message.reply_text(resposta_faq)
    elif sugestoes_faq:
        # Se o FAQ retornou sugestões (incluindo intenções genéricas como "chopp" ou "oi"),
        # apresenta-as como botões inline.
        keyboard = []
        global current_suggestions # Declara para poder modificar o dicionário global
        current_suggestions = {} # Limpa sugestões antigas para esta nova interação

        for i, sugestao_texto in enumerate(sugestoes_faq):
            # O callback_data é um ID simples para o botão, mapeado de volta ao texto completo
            # no dicionário `current_suggestions`.
            callback_key = f"sug:{i}"
            # O texto do botão também não deve ser muito longo, embora o Telegram seja mais flexível com isso.
            keyboard.append([InlineKeyboardButton(sugestao_texto, callback_data=callback_key)])
            current_suggestions[callback_key] = sugestao_texto # Armazena o texto completo da sugestão
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await update.message.reply_text(
                f"🤔 Não entendi bem '{mensagem_original}'. Mas encontrei algumas coisas que podem te interessar:",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Erro ao enviar sugestões com botões para o usuário {user_id}: {e}", exc_info=True)
            await update.message.reply_text(
                "Desculpe, tive um problema ao exibir as sugestões. Por favor, tente reformular sua pergunta ou use os comandos iniciais."
            )
    else:
        # Se nem o FAQ nem as intenções genéricas resolveram, tenta a IA como último recurso.
        await call_ai_api(update, context, mensagem_original)

# --- Configuração Principal do Bot (para python-telegram-bot v20+) ---
def main():
    """Função principal que configura e inicia o bot."""
    # Cria o objeto Application e passa o token do bot.
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Registra os handlers para comandos e callbacks de botões.
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))

    # Lida com todas as mensagens de texto que NÃO são comandos.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot configurado e pronto para iniciar polling...")
    # Inicia o polling para receber atualizações do Telegram.
    # allowed_updates=Update.ALL_TYPES é uma boa prática para desenvolvimento.
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()