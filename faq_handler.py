import json
import unicodedata

# Carrega o FAQ e Apresentação do diretório 'data'.
# Certifique-se de que os arquivos 'faq.json' e 'apresentacao.json' existem e estão acessíveis.
try:
    with open('data/faq.json', 'r', encoding='utf-8') as f:
        FAQ = json.load(f)
except FileNotFoundError:
    FAQ = {}
    print("Aviso: arquivo data/faq.json não encontrado. FAQ estará vazio.")

try:
    with open('data/apresentacao.json', 'r', encoding='utf-8') as f:
        APRESENTACAO = json.load(f)
except FileNotFoundError:
    APRESENTACAO = {"introducao": {"texto": "Bem-vindo!"}, "opcoes": {}, "opcoes_respostas": {}}
    print("Aviso: arquivo data/apresentacao.json não encontrado. Apresentação estará vazia.")


# Função para normalizar texto: converte para minúsculas, remove acentos e divide em tokens.
def normalizar(texto):
    if not isinstance(texto, str):
        texto = str(texto) # Garante que o input seja string
    texto = texto.lower()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    return texto.split()

# Lista de stopwords: palavras comuns que geralmente não agregam significado na busca.
# Elas são removidas para focar nas palavras-chave mais relevantes.
STOPWORDS = set(normalizar("de a o que do da em um para é com no na uma os no e as dos das por eu voce ele ela eles elas nos voces"))

# INTENCOES_GENERICAS: Mapeia termos genéricos ou saudações a um conjunto de sugestões específicas.
# Isso ajuda o bot a fornecer opções direcionadas mesmo para entradas vagas.
INTENCOES_GENERICAS = {
    "oi": ["Onde fica a loja?", "Qual o horário de funcionamento?", "Ver Cardápio", "Quais os tipos de chopp?"],
    "ola": ["Onde fica a loja?", "Qual o horário de funcionamento?", "Ver Cardápio", "Quais os tipos de chopp?"],
    "olá": ["Onde fica a loja?", "Qual o horário de funcionamento?", "Ver Cardápio", "Quais os tipos de chopp?"],
    "bom dia": ["Onde fica a loja?", "Qual o horário de funcionamento?", "Ver Cardápio", "Quais os tipos de chopp?"],
    "boa tarde": ["Onde fica a loja?", "Qual o horário de funcionamento?", "Ver Cardápio", "Quais os tipos de chopp?"],
    "boa noite": ["Onde fica a loja?", "Qual o horário de funcionamento?", "Ver Cardápio", "Quais os tipos de chopp?"],
    "tudo bem": ["Onde fica a loja?", "Qual o horário de funcionamento?", "Ver Cardápio", "Quais os tipos de chopp?"],
    "saudacao": ["Onde fica a loja?", "Qual o horário de funcionamento?", "Ver Cardápio", "Quais os tipos de chopp?"], # Para capturar saudações genéricas
    "chopp": ["Quantos litros de chopp vocês têm?", "Quais tipos de chopp vocês oferecem?", "Como faço para pedir chopp em casa?", "Qual o preço do chopp?"],
    "litro": ["Quantos litros de chopp vocês têm?", "Qual o valor do litro de chopp?", "Vocês vendem barril de 50 litros?"],
    "preco": ["Qual o preço do chopp?", "Valor do litro de chopp?", "Existe promoção de chopp?"],
    "local": ["Qual o endereço da loja?", "Vocês entregam chopp em casa?"],
    "horario": ["Qual o horário de funcionamento da loja?", "Atendem de final de semana?"],
    "litros": ["Quantos litros de chopp vocês têm?", "Qual o valor do litro de chopp?", "Vocês vendem barril de 50 litros?"],
    "cardapio": ["Ver Cardápio", "Onde posso ver o cardápio completo?"],
    "menu": ["Ver Cardápio", "Onde posso ver o cardápio completo?"]
}

# Função principal para responder a uma pergunta ou sugerir opções.
# Retorna uma tupla: (resposta_direta, lista_de_sugestoes).
# Se não houver resposta direta, resposta_direta será None.
def responder_ou_sugerir(pergunta_usuario):
    tokens_usuario = set(normalizar(pergunta_usuario))
    tokens_usuario_sem_stopwords = tokens_usuario - STOPWORDS
    
    # 1. Verificar INTENCOES_GENERICAS primeiro.
    # Se a pergunta do usuário corresponde a uma intenção genérica (como uma saudação ou "chopp"),
    # retorna apenas as sugestões mapeadas para essa intenção.
    pergunta_normalizada_completa = " ".join(normalizar(pergunta_usuario))
    for chave, sugestoes in INTENCOES_GENERICAS.items():
        if chave in pergunta_normalizada_completa:
            # Para saudações mais genéricas, podemos adicionar um check de comprimento para evitar falsos positivos
            if chave in ["oi", "ola", "olá", "bom dia", "boa tarde", "boa noite", "tudo bem"] and len(tokens_usuario) > 3:
                # Se for uma saudação e a frase for mais longa, pode ser uma pergunta real
                continue 
            return None, sugestoes # Retorna None para resposta direta, e as sugestões

    correspondencias = []
    # 2. Procurar por correspondências diretas no FAQ.
    # Itera sobre todos os itens do FAQ para encontrar a melhor correspondência.
    for chave_faq, item_faq in FAQ.items():
        # Combina palavras-chave e a própria pergunta do FAQ para uma busca mais abrangente.
        palavras_chave_faq = set(normalizar(" ".join(item_faq.get("palavras_chave", [])) + " " + item_faq["pergunta"]))
        
        # Calcula a pontuação baseada na quantidade de palavras em comum (intersecção).
        score = len(tokens_usuario_sem_stopwords & palavras_chave_faq)
        
        # Adiciona a correspondência se houver pelo menos uma palavra em comum relevante.
        if score > 0:
            correspondencias.append((score, item_faq))

    # Ordena as correspondências pela pontuação (do maior para o menor).
    correspondences.sort(key=lambda x: x[0], reverse=True)

    if correspondencias:
        melhor_correspondencia = correspondencias[0][1] # Pega o item com a maior pontuação
        resposta_direta = melhor_correspondencia["resposta"]
        
        sugestoes_relacionadas = []
        sugestoes_adicionadas = {melhor_correspondencia["pergunta"]} # Evita sugerir a própria pergunta respondida

        # Pega até 3 sugestões adicionais (as próximas melhores correspondências)
        for score, item_sugestao in correspondencias[1:4]:
            if item_sugestao["pergunta"] not in sugestoes_adicionadas:
                sugestoes_relacionadas.append(item_sugestao["pergunta"])
                sugestoes_adicionadas.add(item_sugestao["pergunta"])

        # Se não houver sugestões relacionadas encontradas, adiciona algumas padrão para "finalizar" a interação.
        if not sugestoes_relacionadas:
            sugestoes_relacionadas = ["Onde fica a loja?", "Qual o horário de funcionamento?", "Ver Cardápio"]

        return resposta_direta, sugestoes_relacionadas
    
    # 3. Se nenhuma resposta direta for encontrada no FAQ nem intenção genérica correspondente,
    # retorna None para a resposta direta e um conjunto de sugestões genéricas padrão.
    # Este é o último recurso antes de chamar a IA, garantindo que o bot sempre oferece opções.
    sugestoes_genericas_padrao = ["Onde fica a loja?", "Qual o horário de funcionamento?", "Ver Cardápio", "Quais os tipos de chopp?", "Falar com humano"]
    return None, sugestoes_genericas_padrao