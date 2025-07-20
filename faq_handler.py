import json
import unicodedata
import os

# Carrega FAQ
with open("data/faq.json", encoding="utf-8") as f:
    faq = json.load(f)

# Função para normalizar texto
def limpar_texto(texto):
    texto = texto.lower()
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    return texto

# Resposta direta ou sugestões
def responder_ou_sugerir(pergunta):
    pergunta_limpa = limpar_texto(pergunta)
    respostas = []
    sugestoes = []

    for item in faq.values():
        palavras_chave = [limpar_texto(p) for p in item["palavras_chave"]]
        if any(p in pergunta_limpa for p in palavras_chave):
            respostas.append(item["resposta"])

    if respostas:
        return respostas[0], []  # Retorna a primeira resposta encontrada

    # Se não encontrou resposta, gera sugestões
    for item in faq.values():
        if any(p in pergunta_limpa for p in item["palavras_chave"][:2]):
            sugestoes.append(item["pergunta"])

    if not sugestoes:
        sugestoes = [item["pergunta"] for item in list(faq.values())[:5]]  # Padrão: 5 perguntas genéricas

    return "", sugestoes
