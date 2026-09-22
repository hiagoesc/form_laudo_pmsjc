"""
Geração do PDF do "Laudo de Vistoria para fins de Regularização, Transformação
de Uso e Solicitação de Atestado de Regularidade da Construção" (PMSJC/DGOP),
reproduzindo o layout do modelo oficial (.doc) o mais próximo possível.

- Página 1: tabelas com bordas (título, identificação, declarações, "acompanha").
- Página seguinte em diante: cabeçalho "RELATÓRIO FOTOGRÁFICO" + fotos em
  caixas de 13 x 9 cm, duas por página, só das categorias que receberam fotos.
- Última página: declaração de fidelidade das fotos + assinaturas.
- QR Codes em blocos (margem de 2 cm das bordas, faixa inferior da página):
    * TODAS as páginas: QR "pg" = código do laudo + data/hora + página p de n
      (é o que permite ao MANARA delimitar início/fim do laudo);
    * página 1, adicionalmente: "imo" (inscrição), "rt" (formação, registro,
      ART/RRT/TRT), "prop" (nome, CPF/CNPJ) e "meta" (uso, atividade, fotos).
  Só vai para os QRs o que é validado por código; o resto fica só impresso.
  Blocos pequenos = QRs de baixa densidade = leitura robusta após impressão
  e scan; e uma falha (carimbo, dobra) derruba só um bloco, não tudo.

Dependências: reportlab, qrcode, Pillow (ver requirements.txt)
"""

import io
import json
import secrets
from datetime import date, datetime
from zoneinfo import ZoneInfo

import qrcode
from PIL import Image as PILImage
from PIL import ImageOps
from qrcode.constants import ERROR_CORRECT_Q
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

FUSO = ZoneInfo("America/Sao_Paulo")
VERSAO_PAYLOAD = 2  # v2: payload em blocos

# --------------------------------------------------------------------------
# Campos de identificação (rótulo do formulário) e chaves curtas do QR
# --------------------------------------------------------------------------

CAMPOS_IDENTIFICACAO = {
    "endereco": "Endereço do imóvel",
    "quadra": "Quadra",
    "lote": "Lote",
    "bairro": "Bairro",
    "inscricao_imobiliaria": "Inscrição imobiliária",
    "formacao": "Formação profissional",
    "responsavel_tecnico": "Nome do Responsável técnico",
    "crea_cau": "Registro no conselho",
    "art_rrt": "Documento de responsabilidade técnica",
    "fone_rt": "Telefone (responsável técnico)",
    "email_rt": "E-mail (responsável técnico)",
    "proprietario": "Nome do Proprietário/possuidor",
    "fone_prop": "Telefone (proprietário/possuidor)",
    "email_prop": "E-mail (proprietário/possuidor)",
    "cpf_cnpj_prop": "CPF/CNPJ (proprietário/possuidor)",
    "uso_imovel": "Qual o uso do imóvel?",
}

DECLARACOES = [
    "Não está localizado em área de risco;",
    "Não está localizada em Áreas de Proteção Ambiental, várzeas ou áreas de "
    "preservação permanente (APP);",
    "Está localizado em loteamento regular e liberado para construção;",
    "Não se trata de invasão de ÁREA PÚBLICA;",
    "Não se trata de área situada em faixas \u201cnon aedificandi\u201d;",
    "Atende às normativas, restrições e licenciamentos pertinentes referente "
    "aos objetos projetados no espaço aéreo, que possam afetar a segurança ou "
    "a regularidade das operações aéreas regulamentadas pelo órgão de "
    "Controle do Espaço Aéreo do Comando da Aeronáutica - Ministério da Defesa;",
    "Apresenta condições de segurança, habitabilidade, higiene e "
    "acessibilidade, ou seja, está em condições para expedição do habite-se "
    "de que trata a Lei em vigor;",
    "Não constam ações demolitória ou de nunciação de obra nova referente ao "
    "imóvel em questão;",
    "*Não consta ações demolitórias ou de usucapião referente ao imóvel em "
    "questão;",
    "*Não se trata de objeto de Incorporação ou Especificação, junto ao "
    "Cartório de Registro de Imóveis.",
]

# --------------------------------------------------------------------------
# Formação profissional -> conselho de classe / documento de RT
# --------------------------------------------------------------------------
FORMACOES = {
    "Arquiteto(a) e Urbanista": {
        "conselho": "CAU", "documento": "RRT", "codigo_qr": "arq",
        "exemplo_conselho": "A123456-7",
        "exemplo_documento": "12345678",
    },
    "Engenheiro(a) Civil": {
        "conselho": "CREA", "documento": "ART", "codigo_qr": "eng",
        # exemplos não incluem o prefixo (CREA/ART) porque o rótulo do campo já mostra
        "exemplo_conselho": "1234567890",
        "exemplo_documento": "1234567890",
    },
    "Técnico(a) em Edificações": {
        "conselho": "CRT", "documento": "TRT", "codigo_qr": "tec",
        "exemplo_conselho": "12345678900",
        "exemplo_documento": "1234567890",
    },
}


def dados_formacao(formacao: str) -> dict:
    return FORMACOES.get(formacao, {
        "conselho": "CREA/CAU/CRT", "documento": "ART/RRT/TRT", "codigo_qr": "",
        "exemplo_conselho": "", "exemplo_documento": "",
    })


# --------------------------------------------------------------------------
# Uso do imóvel: tipo -> categorias; comercial ainda abre a lista de atividades
# --------------------------------------------------------------------------
USO_TIPOS = ["Uso Residencial", "Uso Comercial", "Uso Industrial"]

USO_CATEGORIAS = {
    "Uso Residencial": [
        ("R", "Residencial Unifamiliar"),
        ("RH", "Residencial Multifamiliar Horizontal"),
        ("RHS", "Residencial Horizontal Simples"),
        ("RV1", "Residencial Multifamiliar Vertical"),
        ("RV2", "Residencial Multifamiliar Vertical"),
    ],
    "Uso Comercial": [
        ("CS", "Uso Comercial, de Serviço e Institucional de impacto irrelevante"),
        ("CS1-A", "Uso Comercial, de Serviço e Institucional de impacto baixo"),
        ("CS1-B", "Uso Comercial, de Serviço e Institucional de impacto baixo"),
        ("CS2", "Uso Comercial, de Serviço e Institucional de impacto médio"),
        ("CS3", "Uso Comercial, de Serviço e Institucional de impacto alto"),
        ("CS4-A", "Uso Comercial, de Serviço e Institucional potencial gerador de ruído noturno"),
        ("CS4-B", "Uso Comercial, de Serviço e Institucional potencial gerador de ruído noturno"),
        ("CS5", "Uso Comercial, de Serviço e Institucional específico"),
    ],
    "Uso Industrial": [
        ("I1-A", "Uso industrial de baixo potencial de incomodidade"),
        ("I1-B", "Uso industrial de baixo potencial de incomodidade"),
        ("I2", "Uso industrial de médio potencial de incomodidade"),
        ("I3", "Uso industrial de médio alto potencial de incomodidade"),
        ("I4", "Uso industrial de alto potencial de incomodidade"),
    ],
}

# Categorias comerciais que abrem sub-seleção de atividade (todas exceto CS).
#
# ATENÇÃO — A ORDEM DAS LISTAS É CONTRATO COM O LEITOR (MANARA):
# a atividade vai no QR como posição na lista ("03" = 3º item da categoria).
# Nunca reordene nem remova itens; atividade nova entra SEMPRE no final.
# Se a legislação exigir reorganizar a lista, suba VERSAO_PAYLOAD e mantenha
# a lista antiga disponível no leitor para os laudos já emitidos.
ATIVIDADES_CS = {
    # ------------------------------------------------------------------
    # Impacto baixo, sem análise de localização
    # ------------------------------------------------------------------
    "CS1-A": [
        "Academia de ginástica, escola de dança e música, escola de natação",
        "Blindagem de veículos automotores",
        "Centro de distribuição (depósito) com ACC ≤ 1.000 m²",
        "Cinema, teatro, auditório, sala de convenções, salão para concerto acústico, "
        "TV com auditório — ACC ≥ 600 m²",
        "Comércio atacadista — ACC ≥ 1.000 m²",
        "Comércio de alimentação com drive thru ou que utilize forno com combustível "
        "sólido (lenha, carvão etc.) ou com ACC ≥ 600 m² (restaurante, churrascaria, "
        "pizzaria, padaria etc.)",
        "Comércio de gases medicinais (cilindros)",
        "Comércio de material de construção (sem as operações de corte, lixamento, "
        "polimento)",
        "Edifício comercial e/ou de serviços com uma ou mais unidades (inclusive "
        "shopping center, galerias, boulevard, conjunto de lojas e coworkings) — "
        "ACC ≥ 1.000 m²",
        "Escola de ensino fundamental, médio, técnico, pré-vestibular, superior, "
        "pós-graduação, ensino a distância, cursos profissionalizantes e cursos "
        "livres — ACC ≥ 1.000 m²",
        "Escola infantil, berçário, creche e hotelzinho — ACC ≥ 600 m²",
        "Estacionamento e garagem com área de terreno ≥ 2.500 m² (exceto veículos "
        "pesados)",
        "Hospital, maternidade, pronto-socorro, sanatório e instituição de pesquisa "
        "de doenças",
        "Manutenção e reparação mecânica e elétrica de veículos automotores, "
        "estofaria, conversão de motores e borracharia (exceto veículos pesados)",
        "Martelinho de ouro",
        "Museu e centro cultural — ACC ≥ 1.000 m²",
        "Padaria sem forno a lenha — ACC ≥ 1.000 m²",
        "Pet shop (comércio e serviço) — ACC ≥ 1.000 m²",
        "Prestação de serviços à saúde humana (casa de repouso de idosos, "
        "deficientes físicos, dependentes químicos, assistência psicossocial) — "
        "ACC ≥ 1.000 m²",
        "Recarga e carga (envasamento) de extintor",
        "Revenda de GLP com até 40 unidades (ou 520 kg)",
        "Serviços de atenção ambulatorial sem internação (clínicas médicas e "
        "odontológicas, vacinação e imunização) e demais serviços de saúde "
        "(enfermagem, fisioterapia, psicologia) — ACC ≥ 1.000 m²",
        "Serviço de armazenamento e guarda de bens móveis não associados a "
        "comercialização — ACC ≥ 1.000 m²",
        "Serviços de complementação diagnóstica e terapêutica (análises clínicas, "
        "tomografia, ressonância magnética, radiologia, hemoterapia) — ACC ≥ 1.000 m²",
        "Serviços de hospedagem com ACC ≥ 1.000 m² (hotel, pousada, hostel, albergue "
        "e alojamento)",
        "Showroom com ACC ≥ 1.000 m²",
        "Supermercado, hipermercado, hortifrúti — ACC ≥ 600 m²",
        "Transportadora (somente com o uso de veículos utilitários ou leves)",
        "Templo e local de culto em geral, atividade religiosa",
        "Venda de veículos automotores (exceto caminhões, máquinas agrícolas e "
        "demais veículos pesados)",
        "Aluguel de andaimes com área de terreno ≤ 500 m²",
        "Dedetização, desinfecção, desratização, higienização, controle de pragas "
        "urbanas com armazenamento e/ou fracionamento de produtos com ACC ≤ 250 m²",
        "Lavagem a seco de veículos automotores",
        "Atividade originalmente classificada como CS com ACC ≥ 1.000 m² (regra "
        "geral do Anexo XI, salvo classificação distinta expressa)",
    ],

    # ------------------------------------------------------------------
    # Impacto baixo, com análise de localização
    # ------------------------------------------------------------------
    "CS1-B": [
        "Bar e restaurante sem música após as 22h",
        "Clínica veterinária com internação",
        "Clube esportivo e recreativo",
        "Lanternagem, funilaria e pintura de veículos automotores (exceto veículos "
        "pesados, tais como tratores, caminhões e ônibus)",
        "Lavagem, lubrificação e polimento de veículos automotores (exceto caminhões, "
        "máquinas agrícolas e demais veículos pesados)",
        "Lavanderia hospitalar, lavanderia industrial",
        "Loja e depósito de tinta, verniz, óleo e material lubrificante, com "
        "250 m² < ACC ≤ 500 m²",
        "Posto de abastecimento de veículos em geral",
        "Salão de festas (buffet) infantil, com funcionamento até as 22h",
        "Bar e restaurante com música até as 22h",
        "Ensino e/ou prática de esportes em quadra, com funcionamento até as 22h",
        "Rinque de patinação, pista de skate e boliche, com funcionamento até as 22h",
        "Dedetização, desinfecção, desratização, higienização, controle de pragas "
        "urbanas com armazenamento e/ou fracionamento de produtos com "
        "250 m² < ACC ≤ 500 m²",
        "Tratamento por compostagem e/ou vermicompostagem de resíduos orgânicos "
        "domiciliares de baixo impacto ambiental (quando não exigido licenciamento "
        "ambiental, nos termos da Resolução SIMA n. 69/2020)",
    ],

    # ------------------------------------------------------------------
    # Impacto médio
    # ------------------------------------------------------------------
    "CS2": [
        "Arena ou estádio esportivo",
        "Centro de distribuição de mercadorias (depósito) — ACC > 1.000 m²",
        "Comércio de gases industriais (cilindros)",
        "Comércio de material de construção (com as operações de corte, lixamento e "
        "polimento)",
        "Depósito de banheiro químico portátil",
        "Depósito de material e equipamento de empresa: construtora, tira-entulho, "
        "aluguel de caçamba, aluguel de máquina e equipamento pesado, guarda de "
        "trator, guincho, máquina e equipamento agrícola e demais máquinas de grande "
        "porte",
        "Ensacamento de carvão e venda a granel",
        "Entreposto de carne com câmara frigorífica",
        "Estabelecimentos destinados a criação de animais (canis de criação/estadia, "
        "hotelzinho, pensão ou creche para animais, escola de adestramento)",
        "Dedetização, desinfecção, desratização, higienização, controle de pragas "
        "urbanas com armazenamento e/ou fracionamento de produtos com ACC > 500 m²",
        "Lanternagem, funilaria e pintura de veículos pesados, tais como tratores, "
        "caminhões e ônibus",
        "Lavagem, lubrificação e polimento de veículos pesados, tais como tratores, "
        "caminhões e ônibus",
        "Loja e depósito de tinta, verniz, óleo e material lubrificante — ACC > 500 m²",
        "Manutenção de arma (depende de autorização do Exército)",
        "Manutenção e reparação de embarcações para esporte e lazer",
        "Manutenção e reparação mecânica e elétrica de veículos automotores pesados, "
        "estofaria, conversão de motores e borracharia",
        "Motel e drive-in — AT > 3.000 m²",
        "Ponto/local de entrega, comércio, central de recebimento, ponto de "
        "concentração, transbordo ou triagem de resíduos com baixo potencial de "
        "impacto ambiental (RCC, vidro, papel, papelão, plástico, sucata metálica, "
        "volumosos) — AT < 2.000 m²",
        "Ponto/local de entrega de resíduos envolvidos no sistema de logística "
        "reversa (quando não associada ao ponto de venda) — AT < 2.000 m²",
        "Recondicionamento, recuperação ou retífica de motores para veículos "
        "automotores",
        "Recuperação de extintor de incêndio (desmontagem, jateamento com granalha "
        "de aço, lixamento, pintura por aspersão etc.)",
        "Revenda de GLP entre 40 e 120 unidades (ou até 1.560 kg)",
        "Serviços de desmanche de veículos automotores com comercialização de "
        "partes, peças e acessórios",
        "Stand de tiro (em local fechado)",
        "Transportadora que utiliza veículo de carga; empresa de mudança; garagem de "
        "veículo de carga (ônibus, caminhão); centro de logística",
        "Tratamento por compostagem de resíduos orgânicos domiciliares (quando "
        "exigido licenciamento ambiental, com processamento de até 10 t/dia)",
        "Venda de veículos automotores pesados, tais como tratores, caminhões e ônibus",
        "Airsoft e paintball com funcionamento até as 22h",
        "Aluguel de andaime com AT > 500 m²",
        "Desentupidor e limpa fossa",
        "Central de recebimento, ponto de concentração, transbordo ou triagem de "
        "óleo comestível usado, envolvido no sistema de logística reversa",
    ],

    # ------------------------------------------------------------------
    # Impacto alto
    # ------------------------------------------------------------------
    "CS3": [
        "Base de armazenamento e distribuição de derivados de petróleo e "
        "engarrafadora de GLP",
        "Central de recebimento, ponto de concentração, transbordo ou triagem de "
        "resíduos da logística reversa com potencial de significativo impacto "
        "ambiental (agrotóxicos e embalagens, óleo lubrificante usado e contaminado, "
        "filtros, baterias, eletroeletrônicos, lâmpadas, pneus inservíveis, "
        "medicamentos domiciliares)",
        "Depósito de arma e munição",
        "Depósito e comércio de produtos perigosos: químico, inflamável e explosivo",
        "Desentupidora e limpa fossa",
        "Estacionamento e garagem de veículos pesados",
        "Estande de tiro (em local aberto)",
        "Laboratório de ensaio destrutivo",
        "Loja de fogos de artifício e de estampido (no máximo 25 kg de pólvora de caça)",
        "Oficina de recondicionamento e recuperação de bateria",
        "Ponto/local de entrega, comércio, central de recebimento, ponto de "
        "concentração, transbordo ou triagem de resíduos com baixo potencial de "
        "impacto ambiental — AT ≥ 2.000 m²",
        "Ponto/local de entrega de resíduos envolvidos no sistema de logística "
        "reversa (quando não associada ao ponto de venda) — AT ≥ 2.000 m²",
        "Revenda de GLP com mais de 120 unidades",
        "Transportadora de derivados de petróleo, produto inflamável, explosivo, "
        "perigoso e de resíduo sólido urbano",
        "Tratamento e/ou disposição de resíduos sólidos (aterramento, compostagem de "
        "resíduos orgânicos não domiciliares, preparo de CDR, estabilização por "
        "processos aeróbios ou anaeróbios, biodigestão, processos mecânico-biológicos)",
        "Tratamento por compostagem de resíduos orgânicos domiciliares (quando "
        "exigido licenciamento ambiental, com processamento acima de 10 t/dia e até "
        "100 t/dia) — somente na ZUPI2",
    ],

    # ------------------------------------------------------------------
    # Gerador de ruído noturno
    # ------------------------------------------------------------------
    "CS4-A": [
        "Boate, danceteria, salão de festas",
        "Restaurante, bar noturno, karaokê e similares com música após as 22h",
        "Prática de esportes em quadra, com funcionamento após as 22h",
    ],

    "CS4-B": [
        "Casa de shows, eventos e/ou espetáculos",
        "Quadra de escola de samba e congêneres",
        "Rinque de patinação, pista de skate e boliche, com funcionamento após as 22h",
    ],

    # ------------------------------------------------------------------
    # Sujeito a análise específica
    # ------------------------------------------------------------------
    "CS5": [
        "Abastecimento de gás natural (estações, centrais)",
        "Autódromo, pista de motocross, kartódromo, kart indoor, velódromo, hípica",
        "Equipamentos relacionados à mobilidade urbana (terminais de ônibus urbano e "
        "interurbano, estações de transporte coletivo)",
        "Equipamentos relacionados ao transporte aéreo (aeroportos, aeródromos e "
        "helipontos)",
        "Geração, transmissão e distribuição de energia elétrica (estações e "
        "subestações, sistemas de transmissão e usinas de geração)",
        "Parque temático e/ou de diversões permanente, zoológico, centro e/ou "
        "pavilhão de feira e/ou exposição",
        "Saneamento ambiental (estação de tratamento de água e de esgoto, estação "
        "elevatória de água e esgoto, entre outros)",
        "Unidade de internação, treinamento e recuperação de menor infrator, cadeia "
        "e presídio",
        "Velório, serviço de tanatopraxia, necrotério, crematório e cemitério",
    ],
}


def codigo_atividade(sigla: str, atividade: str) -> str:
    """Posição (1-based, 2 dígitos) da atividade na lista da categoria: '03'."""
    return f"{ATIVIDADES_CS[sigla].index(atividade) + 1:02d}"


def atividade_por_codigo(sigla: str, codigo: str):
    """Inverso de codigo_atividade — para o leitor. None se não existir."""
    lista = ATIVIDADES_CS.get(sigla) or []
    try:
        i = int(codigo) - 1
    except (TypeError, ValueError):
        return None
    return lista[i] if 0 <= i < len(lista) else None


# --------------------------------------------------------------------------
# CPF / CNPJ
# --------------------------------------------------------------------------

def _digitos(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _cpf_valido(d: str) -> bool:
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def _cnpj_valido(d: str) -> bool:
    if len(d) != 14 or d == d[0] * 14:
        return False
    for n, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]),
                     (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        resto = sum(int(d[i]) * pesos[i] for i in range(n)) % 11
        if (0 if resto < 2 else 11 - resto) != int(d[n]):
            return False
    return True


def validar_cpf_cnpj(texto: str):
    """Retorna (tipo, digitos) com tipo 'cpf' ou 'cnpj'; (None, digitos) se inválido."""
    d = _digitos(texto)
    if _cpf_valido(d):
        return "cpf", d
    if _cnpj_valido(d):
        return "cnpj", d
    return None, d


def formatar_cpf_cnpj(texto: str) -> str:
    tipo, d = validar_cpf_cnpj(texto)
    if tipo == "cpf":
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if tipo == "cnpj":
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return texto or ""


def montar_uso_imovel(codigo: str, descricao: str, atividade=None) -> str:
    """Texto que aparece impresso no laudo: código + descrição + atividade (se houver)."""
    texto = f"({codigo}) {descricao}"
    if atividade:
        texto += f" — Atividade: {atividade}"
    return texto


# id do slot -> (rótulo exibido, fonte é "imagem" Google?, data atual por padrão?)
CATEGORIAS_FOTO = [
    {"codigo": "aa", "titulo": "IMAGEM AÉREA ATUAL COM A IDENTIFICAÇÃO DO IMÓVEL",
     "fonte_padrao": "Google Earth", "data_atual_padrao": True},
    {"codigo": "a6", "titulo": "IMAGEM AÉREA DE 6 ANOS ATRÁS IDENTIFICANDO O IMÓVEL",
     "fonte_padrao": "Google Earth", "data_atual_padrao": False},
    {"codigo": "ff", "titulo": "FOTO DA FACHADA FRONTAL ATUAL",
     "fonte_imagem": False, "data_atual_padrao": True},
    {"codigo": "f6", "titulo": "FOTO DA FACHADA FRONTAL HÁ 6 ANOS ATRÁS",
     "fonte_padrao": "Google Street View", "data_atual_padrao": False},
    {"codigo": "ld", "titulo": "FOTO DA FACHADA E RECUO LATERAL DIREITO",
     "fonte_imagem": False, "data_atual_padrao": True},
    {"codigo": "le", "titulo": "FOTO DA FACHADA E RECUO LATERAL ESQUERDO",
     "fonte_imagem": False, "data_atual_padrao": True},
    {"codigo": "fu", "titulo": "FOTO DA FACHADA DE FUNDOS",
     "fonte_imagem": False, "data_atual_padrao": True},
    {"codigo": "rf", "titulo": "FOTO DO RECUO DE FUNDOS/EDÍCULA",
     "fonte_imagem": False, "data_atual_padrao": True},
    {"codigo": "ba", "titulo": "FOTO DOS BANHEIROS",
     "fonte_imagem": False, "data_atual_padrao": True},
    {"codigo": "dc", "titulo": "FOTO DOS DEMAIS COMPARTIMENTOS DA EDIFICAÇÃO",
     "fonte_imagem": False, "data_atual_padrao": True},
    {"codigo": "ab", "titulo": "FOTO DOS ABRIGOS DESMONTÁVEIS",
     "fonte_imagem": False, "data_atual_padrao": True},
    {"codigo": "va", "titulo": "FOTO DAS VAGAS DE ESTACIONAMENTO",
     "fonte_imagem": False, "data_atual_padrao": True},
]
CODIGO_DIVERSAS = "dv"  # categorias livres criadas pelo profissional
FONTES_IMAGEM = ["Google Earth", "Google Street View", "Outra"]
FONTE_AUTOR = "Elaborado pelo autor"

# --------------------------------------------------------------------------
# Geometria da página
# --------------------------------------------------------------------------
LARG_PAG, ALT_PAG = A4
MARGEM_LAT = 1.8 * cm
MARGEM_TOPO = 1.3 * cm
QR_TAMANHO = 3.0 * cm        # cada QR de bloco (todos são pequenos: ≤ ~110 bytes)
QR_MARGEM = 2.0 * cm          # exigência: 2 cm da borda => fora da zona do carimbo SIPEX
QR_LADO = "esquerda"          # lado do QR "pg" nas páginas 2..n: "esquerda" ou "direita"
MARGEM_BASE = QR_MARGEM + QR_TAMANHO + 0.3 * cm  # faixa inferior reservada aos QRs
LARG_UTIL = LARG_PAG - 2 * MARGEM_LAT
CAIXA_FOTO_L, CAIXA_FOTO_A = 13 * cm, 9 * cm     # 9 x 13 cm, paisagem, como no modelo


def agora() -> datetime:
    return datetime.now(FUSO)


# --------------------------------------------------------------------------
# QR Code
# --------------------------------------------------------------------------

def _limpo(v):
    return v.strip() if isinstance(v, str) else v


def _sem_vazios(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "", [])}


def montar_blocos(dados: dict, categorias: list, doc_id: str) -> dict:
    """Payloads dos QRs de dados da página 1, por bloco.
    Todos carregam v (versão), d (código do laudo) e b (bloco) para o leitor
    juntar os pedaços do mesmo laudo."""
    base = {"v": VERSAO_PAYLOAD, "d": doc_id}
    tipo_doc, digitos_doc = validar_cpf_cnpj(dados.get("cpf_cnpj_prop"))
    ordem = [c["codigo"] for c in CATEGORIAS_FOTO] + [CODIGO_DIVERSAS]
    presentes = {cat["codigo"] for cat in categorias if cat.get("itens")}
    return {
        "imo": _sem_vazios({**base, "b": "imo", "ins": _limpo(dados.get("inscricao_imobiliaria"))}),
        "rt": _sem_vazios({**base, "b": "rt",
                           "f": dados_formacao(dados.get("formacao"))["codigo_qr"],
                           "reg": _limpo(dados.get("crea_cau")),
                           "art": _limpo(dados.get("art_rrt"))}),
        "prop": _sem_vazios({**base, "b": "prop",
                             "nm": _limpo(dados.get("proprietario")),
                             (tipo_doc or "cpf"): digitos_doc}),
        "meta": _sem_vazios({**base, "b": "meta",
                             "uso": dados.get("uso_codigo"),
                             "atv": dados.get("uso_atividade_cod"),
                             "cat": [cod for cod in ordem if cod in presentes]}),
    }


def payload_pagina(doc_id: str, ts: datetime, p: int, n: int) -> dict:
    """QR presente em TODAS as páginas: identifica o laudo e a posição da página."""
    return {"v": VERSAO_PAYLOAD, "d": doc_id, "b": "pg",
            "ts": ts.strftime("%Y-%m-%dT%H:%M:%S%z"), "p": p, "n": n}


def flags_categorias(payload: dict) -> dict:
    """Lado da leitura (MANARA): expande payload['cat'] em {codigo: bool}."""
    ordem = [c["codigo"] for c in CATEGORIAS_FOTO] + [CODIGO_DIVERSAS]
    presentes = set(payload.get("cat") or [])
    return {cod: cod in presentes for cod in ordem}


def _qr_png(payload: dict) -> io.BytesIO:
    texto = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_Q, box_size=6, border=2)
    qr.add_data(texto)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# --------------------------------------------------------------------------
# Tratamento de imagem (EXIF, redução) e caixa de foto 13 x 9 cm
# --------------------------------------------------------------------------

def _preparar_foto(arquivo, max_lado=1600) -> io.BytesIO:
    """Corrige orientação EXIF (foto de celular) e limita resolução para não
    inflar o PDF; 1600 px no maior lado dá > 300 dpi numa caixa de 13 cm."""
    arquivo.seek(0)
    img = PILImage.open(arquivo)
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    img.thumbnail((max_lado, max_lado))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    buf.seek(0)
    return buf


class CaixaFoto(Flowable):
    """Retângulo de 13 x 9 cm centralizado na página, com a foto ajustada
    (proporção preservada) dentro dele — espelha a caixa do modelo."""

    def __init__(self, foto_buf, largura_total, caixa_l=CAIXA_FOTO_L, caixa_a=CAIXA_FOTO_A):
        super().__init__()
        self.reader = ImageReader(foto_buf)
        self.largura_total = largura_total
        self.caixa_l, self.caixa_a = caixa_l, caixa_a
        self.width, self.height = largura_total, caixa_a

    def draw(self):
        c = self.canv
        x0 = (self.largura_total - self.caixa_l) / 2
        c.setLineWidth(0.6)
        c.rect(x0, 0, self.caixa_l, self.caixa_a)
        iw, ih = self.reader.getSize()
        escala = min((self.caixa_l - 4) / iw, (self.caixa_a - 4) / ih)
        w, h = iw * escala, ih * escala
        c.drawImage(self.reader, x0 + (self.caixa_l - w) / 2, (self.caixa_a - h) / 2, w, h)


# --------------------------------------------------------------------------
# Estilos e tabelas da página 1
# --------------------------------------------------------------------------

def _estilos():
    base = getSampleStyleSheet()["Normal"]
    return {
        "titulo": ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=9, leading=12, alignment=TA_CENTER),
        "campo": ParagraphStyle("c", parent=base, fontSize=9, leading=12, wordWrap="CJK"),
        "decl": ParagraphStyle("d", parent=base, fontSize=9, leading=12, leftIndent=0.9 * cm),
        "decl_intro": ParagraphStyle("di", parent=base, fontName="Helvetica-Bold", fontSize=9, leading=12, leftIndent=0.9 * cm),
        "nota": ParagraphStyle("n", parent=base, fontSize=7, leading=9, leftIndent=0.9 * cm),
        "foto_titulo": ParagraphStyle("ft", parent=base, fontSize=9, leading=12, alignment=TA_CENTER),
        "foto_legenda": ParagraphStyle("fl", parent=base, fontSize=9, leading=12, leftIndent=(LARG_UTIL - CAIXA_FOTO_L) / 2),
        "texto": ParagraphStyle("x", parent=base, fontSize=9, leading=12, wordWrap="CJK"),
        "texto_centro": ParagraphStyle("xc", parent=base, fontSize=9, leading=12, alignment=TA_CENTER),
    }


def _bloco(linhas, col_widths, st):
    """Tabela com borda externa + linhas horizontais, como no modelo."""
    t = Table(linhas, colWidths=col_widths)
    estilo = [
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    t.setStyle(TableStyle(estilo + st))
    return t


def _expoentes(texto: str) -> str:
    """As fontes padrão do reportlab (Helvetica) não têm os glifos ² e ³: eles
    somem do PDF impresso (embora fiquem no texto). Converte para <super>,
    que o Paragraph renderiza sem depender de fonte externa."""
    return (texto or "").replace("²", "<super>2</super>").replace("³", "<super>3</super>")


def _campo(rotulo, dados, chave, st):
    valor = _expoentes(dados.get(chave, "") or "")
    return Paragraph(f"{rotulo}: {valor}", st["campo"])


def _cabecalho(texto, st):
    return Paragraph(f"<b>{texto}</b>", st["campo"])


def _pagina1(dados, st):
    """Página 1: blocos com borda, cada um com linha de cabeçalho em negrito.
    Em todos os blocos a linha 0 é o cabeçalho (ocupando a largura toda)."""
    story = []
    w = LARG_UTIL
    formacao = dados_formacao(dados.get("formacao"))
    espaco = Spacer(1, 0.3 * cm)

    story.append(_bloco(
        [[Paragraph("LAUDO DE VISTORIA PARA FINS DE REGULARIZAÇÃO, TRANSFORMAÇÃO DE USO E "
                    "SOLICITAÇÃO DE ATESTADO DE REGULARIDADE DA CONSTRUÇÃO JUNTO À PMSJC", st["titulo"])]],
        [w], [("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(Spacer(1, 0.5 * cm))

    # Dados do imóvel — inscrição primeiro (é o dado que valida o imóvel)
    story.append(_bloco(
        [[_cabecalho("DADOS DO IMÓVEL", st), "", ""],
         [_campo("INSCRIÇÃO IMOBILIÁRIA", dados, "inscricao_imobiliaria", st), "", ""],
         [_campo("ENDEREÇO", dados, "endereco", st), "", ""],
         [_campo("QUADRA", dados, "quadra", st), _campo("LOTE", dados, "lote", st), _campo("BAIRRO", dados, "bairro", st)]],
        [w * 0.38, w * 0.24, w * 0.38],
        [("SPAN", (0, 0), (-1, 0)), ("SPAN", (0, 1), (-1, 1)), ("SPAN", (0, 2), (-1, 2)),
         ("LINEBEFORE", (1, 3), (2, 3), 0.5, colors.black)]))
    story.append(espaco)

    # Responsável técnico — rótulos de conselho/documento dependem da formação
    story.append(_bloco(
        [[_cabecalho("RESPONSÁVEL TÉCNICO", st), ""],
         [_campo("NOME", dados, "responsavel_tecnico", st), ""],
         [_campo(formacao["conselho"], dados, "crea_cau", st), _campo(formacao["documento"], dados, "art_rrt", st)],
         [_campo("TELEFONE", dados, "fone_rt", st), _campo("E-MAIL", dados, "email_rt", st)]],
        [w * 0.62, w * 0.38],
        [("SPAN", (0, 0), (-1, 0)), ("SPAN", (0, 1), (-1, 1)),
         ("LINEBEFORE", (1, 2), (1, 3), 0.5, colors.black)]))
    story.append(espaco)

    # Proprietário/possuidor
    story.append(_bloco(
        [[_cabecalho("PROPRIETÁRIO/POSSUIDOR", st), ""],
         [_campo("NOME", dados, "proprietario", st),
          Paragraph(f"CPF/CNPJ: {formatar_cpf_cnpj(dados.get('cpf_cnpj_prop'))}", st["campo"])],
         [_campo("TELEFONE", dados, "fone_prop", st), _campo("E-MAIL", dados, "email_prop", st)]],
        [w * 0.62, w * 0.38],
        [("SPAN", (0, 0), (-1, 0)), ("LINEBEFORE", (1, 1), (1, 2), 0.5, colors.black)]))
    story.append(espaco)

    # Uso do imóvel
    story.append(_bloco(
        [[_cabecalho("USO DO IMÓVEL", st)],
         [Paragraph(_expoentes(dados.get("uso_imovel")), st["campo"])]],
        [w], []))
    story.append(espaco)

    # Declarações
    decl = [Paragraph("Declaramos que o imóvel descrito atende as condições abaixo:", st["decl"])]
    decl += [Paragraph(f"{i}. {txt}", st["decl"]) for i, txt in enumerate(DECLARACOES, start=1)]
    decl.append(Paragraph("* itens aplicáveis para os casos de atestado de regularidade da construção", st["nota"]))
    story.append(_bloco(
        [[_cabecalho("DECLARAÇÕES", st)], [decl]],
        [w], [("TOPPADDING", (0, 1), (-1, 1), 5), ("BOTTOMPADDING", (0, 1), (-1, 1), 6)]))
    story.append(espaco)

    # Anexo
    story.append(_bloco(
        [[_cabecalho("ANEXO", st)],
         [Paragraph("O presente laudo acompanha:<br/>1- PROJETO COM A DESCRIÇÃO DAS ÁREAS REGULARMENTE "
                    "EXISTENTES E AS ÁREAS A REGULARIZAR, CONFORME MODELO DE PROJETO DISPONÍVEL NO SITE "
                    "DA PREFEITURA", st["campo"])]],
        [w], []))
    return story


def _cabecalho_fotos(st):
    return _bloco(
        [[Paragraph("<b>RELATÓRIO FOTOGRÁFICO</b><br/>O relatório fotográfico deverá conter fotos relevantes que "
                    "esclareçam a situação das construções existentes, mostrando as fachadas, os ambientes internos "
                    "e revestimentos nas áreas úmidas, estacionamento com demarcação de vagas e acessibilidade no "
                    "uso não residencial.", st["texto_centro"])]],
        [LARG_UTIL], [("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)])


def _formatar_data(d) -> str:
    if isinstance(d, (date, datetime)):
        return d.strftime("%d/%m/%Y")
    return str(d or "")


def _blocos_fotos(categorias, st):
    """Um bloco (título + caixa + legenda) por foto; só categorias com fotos."""
    story = []
    for cat in categorias:
        itens = cat.get("itens") or []
        if not itens:
            continue
        for item in itens:
            foto = _preparar_foto(item["arquivo"])
            legenda = _expoentes(f"Fonte: {item.get('fonte') or '—'} — Data: {_formatar_data(item.get('data'))}")
            story.append(KeepTogether([
                Paragraph(_expoentes(cat["titulo"]), st["foto_titulo"]),
                Spacer(1, 0.1 * cm),
                CaixaFoto(foto, LARG_UTIL),
                Spacer(1, 0.05 * cm),
                Paragraph(legenda, st["foto_legenda"]),
                Spacer(1, 0.45 * cm),
            ]))
    return story


def _assinaturas(dados, st):
    formacao = dados_formacao(dados.get("formacao"))
    rotulo_conselho = formacao["conselho"]

    def p(txt):
        return Paragraph(txt, st["texto"])

    gutter = LARG_UTIL * 0.06
    col = (LARG_UTIL - gutter) / 2
    tabela = Table(
        [
            ["", "", ""],
            [p(f"Responsável Técnico: {dados.get('responsavel_tecnico') or ''}"), "",
             p(f"Proprietário/Possuidor: {dados.get('proprietario') or ''}")],
            [p(f"{rotulo_conselho}: {dados.get('crea_cau') or ''}"), "",
             p(f"CPF/CNPJ: {formatar_cpf_cnpj(dados.get('cpf_cnpj_prop'))}")],
        ],
        colWidths=[col, gutter, col],
    )
    tabela.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (0, 0), 0.8, colors.black),
        ("LINEABOVE", (2, 0), (2, 0), 0.8, colors.black),
        ("TOPPADDING", (0, 0), (-1, 0), 0),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return KeepTogether([
        Paragraph("Declaramos que as fotos apresentadas são fiéis ao edificado no imóvel.", st["texto"]),
        Spacer(1, 1.4 * cm),
        tabela,
    ])


# --------------------------------------------------------------------------
# Rodapé de cada página: QR + número de página
# --------------------------------------------------------------------------

ROTULOS_BLOCO = {"pg": "Laudo/página", "imo": "Imóvel", "rt": "Resp. técnico",
                 "prop": "Proprietário", "meta": "Uso/fotos"}


class _Rodape:
    """Desenha os QRs na faixa inferior de cada página (callback do Platypus).
    Página 1: pg + 4 blocos de dados, lado a lado entre as margens de 2 cm.
    Demais páginas: só o QR "pg", no lado definido por QR_LADO."""

    def __init__(self, blocos: dict, doc_id: str, ts: datetime, total_paginas):
        self.blocos, self.doc_id, self.ts, self.total = blocos, doc_id, ts, total_paginas
        # QRs dos blocos de dados não mudam entre páginas nem entre passadas: gera uma vez
        self._png_blocos = {nome: _qr_png(pl).getvalue() for nome, pl in blocos.items()}

    def _desenhar(self, canv, png_bytes, x, rotulo):
        canv.drawImage(ImageReader(io.BytesIO(png_bytes)), x, QR_MARGEM, QR_TAMANHO, QR_TAMANHO)
        canv.setFont("Helvetica", 6)
        canv.drawCentredString(x + QR_TAMANHO / 2, QR_MARGEM - 0.3 * cm, rotulo)

    def __call__(self, canv, doc):
        p = canv.getPageNumber()
        png_pg = _qr_png(payload_pagina(self.doc_id, self.ts, p, self.total or 0)).getvalue()
        rotulo_pg = f"Laudo {self.doc_id} · pág. {p}/{self.total or '?'}"

        if p == 1:
            itens = [("pg", png_pg, rotulo_pg)] + [
                (nome, self._png_blocos[nome], ROTULOS_BLOCO[nome]) for nome in ("imo", "rt", "prop", "meta")]
            largura = LARG_PAG - 2 * QR_MARGEM
            passo = (largura - QR_TAMANHO) / (len(itens) - 1)
            for i, (_, png, rotulo) in enumerate(itens):
                self._desenhar(canv, png, QR_MARGEM + i * passo, rotulo)
        else:
            x = QR_MARGEM if QR_LADO == "esquerda" else LARG_PAG - QR_MARGEM - QR_TAMANHO
            self._desenhar(canv, png_pg, x, rotulo_pg)

        canv.setFont("Helvetica", 9)
        canv.drawRightString(LARG_PAG - MARGEM_LAT, 1.2 * cm, str(p))


# --------------------------------------------------------------------------
# Geração principal
# --------------------------------------------------------------------------

def gerar_pdf(dados: dict, categorias: list) -> dict:
    """
    dados: dict com as chaves de CAMPOS_IDENTIFICACAO, mais "uso_codigo"
        (sigla da categoria de uso) e "uso_atividade_cod" ("03" ou None) — só
        esses dois vão para o QR; o texto completo do uso vai impresso.
    categorias: lista ordenada de dicts
        {"codigo": str, "titulo": str,
         "itens": [ {"arquivo": file-like, "fonte": str, "data": date}, ... ]}
        Categorias livres ("fotos diversas") usam codigo = CODIGO_DIVERSAS.

    Retorna {"pdf": bytes, "blocos": dict, "paginas": int, "doc_id": str, "gerado_em": datetime}
    """
    ts = agora()
    doc_id = secrets.token_hex(4)  # 8 hex — identificador do laudo dentro do QR
    blocos = montar_blocos(dados, categorias, doc_id)
    st = _estilos()

    def montar_story():
        story = _pagina1(dados, st)
        story.append(PageBreak())
        story.append(_cabecalho_fotos(st))
        story.append(Spacer(1, 0.4 * cm))
        story += _blocos_fotos(categorias, st)
        story.append(_assinaturas(dados, st))
        return story

    def construir(total):
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=MARGEM_LAT, rightMargin=MARGEM_LAT,
            topMargin=MARGEM_TOPO, bottomMargin=MARGEM_BASE,
            title="Laudo de vistoria para fins de regularização — PMSJC",
        )
        rodape = _Rodape(blocos, doc_id, ts, total)
        doc.build(montar_story(), onFirstPage=rodape, onLaterPages=rodape)
        return buf.getvalue(), doc.page

    # Duas passagens: a primeira só para descobrir o total de páginas (n),
    # a segunda gera os QRs já com "p de n" corretos.
    _, total = construir(None)
    pdf_bytes, total = construir(total)

    return {"pdf": pdf_bytes, "blocos": blocos, "paginas": total,
            "doc_id": doc_id, "gerado_em": ts}
