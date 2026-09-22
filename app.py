"""
Formulário para preenchimento de laudo de vistoria padrão para Regularização /
Atestado de Regularidade na PMSJC (DGOP).

Roda 100% na sessão do navegador do profissional responsável técnico: nenhum
dado é salvo em banco nem enviado online.

O profissional preenche, anexa as fotos, baixa o PDF (com QR Code em todas as
páginas) e preferencialmente assina eletronicamente (via gov.br por exemplo)
ou imprime, assina à mão e escaneia para protocolar junto ao processo.

Rodar localmente:   streamlit run app.py
Deploy gratuito:    ver README.md (Streamlit Community Cloud)
"""

import streamlit as st

from pdf_generator import (
    ATIVIDADES_CS,
    CAMPOS_IDENTIFICACAO,
    CATEGORIAS_FOTO,
    CODIGO_DIVERSAS,
    DECLARACOES,
    FONTE_AUTOR,
    FORMACOES,
    USO_CATEGORIAS,
    USO_TIPOS,
    agora,
    codigo_atividade,
    dados_formacao,
    formatar_cpf_cnpj,
    gerar_pdf,
    montar_uso_imovel,
    validar_cpf_cnpj,
)

st.set_page_config(page_title="Laudo de Regularização — DGOP/PMSJC", page_icon="🏗️", layout="centered")

st.header("Laudo de vistoria padrão para Regularização / Atestado de Regularidade na PMSJC")
st.caption(
    "Este é um formulário para preenchimento de dados para elaboração de laudo de "
    "vistoria no padrão do Departamento de Gestão de Obras Particulares da "
    "Prefeitura de São José dos Campos para Regularização / Atestado de Regularidade."
)
st.caption(
    "Trata-se de ferramenta independente: nenhum dado é obtido ou enviado aos bancos"
    " de dados da Prefeitura por este formulário. Este utilitário gera um arquivo PD"
    "F com os dados preenchidos e fotos anexadas, acompanhados de QR Codes que faci"
    "litam a leitura dos dados do laudo por meio eletrônico para conferência."
)
st.caption(
    "O documento gerado deve ser assinado preferencialmente por meio eletrônico (via"
    " gov.br, por exemplo), ou impresso, assinado à mão e escaneado para protocolar "
    "junto ao respectivo processo."
)

HOJE = agora().date()

# --------------------------------------------------------------------------
# 1. Dados de identificação
# --------------------------------------------------------------------------
st.subheader("1. Dados do imóvel")
dados = {}
dados["inscricao_imobiliaria"] = st.text_input(
    CAMPOS_IDENTIFICACAO["inscricao_imobiliaria"], placeholder="Ex.: 00.0000.0000.0000"
)
dados["endereco"] = st.text_input(CAMPOS_IDENTIFICACAO["endereco"], placeholder="Ex.: R. José de Alencar, 123")
c1, c2, c3 = st.columns(3)
dados["quadra"] = c1.text_input(CAMPOS_IDENTIFICACAO["quadra"], placeholder="Ex.: A")
dados["lote"] = c2.text_input(CAMPOS_IDENTIFICACAO["lote"], placeholder="Ex.: 01")
dados["bairro"] = c3.text_input(CAMPOS_IDENTIFICACAO["bairro"], placeholder="Ex.: Vila Santa Luzia")

st.subheader("2. Responsável técnico")
formacao = st.selectbox("Formação profissional", list(FORMACOES.keys()))
dados["formacao"] = formacao
info_formacao = dados_formacao(formacao)

dados["responsavel_tecnico"] = st.text_input(
    CAMPOS_IDENTIFICACAO["responsavel_tecnico"], placeholder="Ex.: João da Silva"
)
c4, c5 = st.columns(2)
dados["crea_cau"] = c4.text_input(info_formacao["conselho"], placeholder=f"Ex.: {info_formacao['exemplo_conselho']}")
dados["art_rrt"] = c5.text_input(info_formacao["documento"], placeholder=f"Ex.: {info_formacao['exemplo_documento']}")
c6, c7 = st.columns(2)
dados["fone_rt"] = c6.text_input(CAMPOS_IDENTIFICACAO["fone_rt"], placeholder="Ex.: (12) 99999-0000")
dados["email_rt"] = c7.text_input(CAMPOS_IDENTIFICACAO["email_rt"], placeholder="Ex.: joao.silva@email.com")

st.subheader("3. Proprietário/possuidor")
cp1, cp2 = st.columns([2, 1])
dados["proprietario"] = cp1.text_input(CAMPOS_IDENTIFICACAO["proprietario"], placeholder="Ex.: Maria dos Santos")
dados["cpf_cnpj_prop"] = cp2.text_input(
    CAMPOS_IDENTIFICACAO["cpf_cnpj_prop"], placeholder="Ex.: 000.000.000-00",
    help="CPF (pessoa física) ou CNPJ (pessoa jurídica). Pode digitar só os números.")
tipo_doc_prop, _ = validar_cpf_cnpj(dados["cpf_cnpj_prop"])
if dados["cpf_cnpj_prop"] and not tipo_doc_prop:
    cp2.error("CPF/CNPJ inválido — confira os dígitos.")
elif tipo_doc_prop:
    cp2.caption(f"{tipo_doc_prop.upper()} válido: {formatar_cpf_cnpj(dados['cpf_cnpj_prop'])}")
c8, c9 = st.columns(2)
dados["fone_prop"] = c8.text_input(CAMPOS_IDENTIFICACAO["fone_prop"], placeholder="Ex.: (12) 98888-0000")
dados["email_prop"] = c9.text_input(CAMPOS_IDENTIFICACAO["email_prop"], placeholder="Ex.: maria.souza@email.com")

st.subheader("4. Uso do imóvel")
tipo_uso = st.selectbox("Tipo de uso", USO_TIPOS)
opcoes_categoria = USO_CATEGORIAS[tipo_uso]
codigo_cat, desc_cat = st.selectbox(
    "Categoria", opcoes_categoria, format_func=lambda par: f"({par[0]}) {par[1]}"
)
atividade = None
if codigo_cat in ATIVIDADES_CS:
    atividade = st.selectbox(
        "Atividade", ATIVIDADES_CS[codigo_cat],
        format_func=lambda a: f"{codigo_atividade(codigo_cat, a)} — {a}")
dados["uso_codigo"] = codigo_cat
dados["uso_atividade_cod"] = codigo_atividade(codigo_cat, atividade) if atividade else None
dados["uso_imovel"] = montar_uso_imovel(codigo_cat, desc_cat, atividade)
st.caption(f"Vai para o laudo: **{dados['uso_imovel']}**")

# --------------------------------------------------------------------------
# 2. Declaração
# --------------------------------------------------------------------------
st.subheader("5. Declaração")
st.markdown("Declaramos que o imóvel descrito atende as condições abaixo:")
st.markdown("\n".join(f"{i}. {t}" for i, t in enumerate(DECLARACOES, start=1)))
st.caption("\\* itens aplicáveis para os casos de atestado de regularidade da construção")
declaracao_confirmada = st.checkbox("Confirmo, como responsável técnico, que o imóvel atende às condições acima.")

# --------------------------------------------------------------------------
# 3. Relatório fotográfico
# --------------------------------------------------------------------------
st.subheader("6. Relatório fotográfico")
st.caption(
    "Para cada categoria abaixo, anexe quantas fotos forem necessárias para auxiliar na "
    "análise do respectivo processo."
)
st.caption(
    "Para o caso de o imóvel não corresponder a alguma das categorias, não é necessário "
    "anexar fotos, categorias vazias não entram no laudo."
)
st.caption(
    "Cada foto deve conter indicação da sua fonte e da sua data de origem. Por padrão, "
    "as fotos gerais vêm com indicação 'Fonte: Elaborado pelo autor' e a data atual. "
    "Caso seja necessário alterar, desmarque o 'check' que irá surgir campo para "
    "edição. As imagens aéreas vêm por padrão 'Fonte: Google Earth' e a foto da fachada "
    "frontal há 6 anos atrás vem 'Fonte: Google Street View', também sendo possível "
    "alterar."
)
st.caption(
    "Caso seja necessária alguma categoria além das indicadas, use o 'Adicionar categori"
    "a' logo abaixo."
)


def _controles_foto(chave: str, arquivo, cat: dict) -> dict:
    """Fonte + data de uma foto. Regras:
    - fonte: check com a fonte padrão da categoria (Google Earth nas imagens
      aéreas, Google Street View na fachada de 6 anos atrás, "Elaborado pelo
      autor" nas demais); desmarcando, abre campo de texto livre;
    - data: check "Data atual" (padrão conforme a categoria) ou data manual."""
    col_img, col_ctl = st.columns([1, 2])
    col_img.image(arquivo, width=180)
    with col_ctl:
        # Fonte padrão da categoria (Google Earth / Google Street View / Elaborado pelo autor);
        # desmarcando o check, abre campo para digitar outra fonte.
        fonte_padrao = cat.get("fonte_padrao", FONTE_AUTOR)
        usar_padrao = st.checkbox(f"Fonte: {fonte_padrao}", value=True, key=f"{chave}_autor")
        exemplo = "Ex.: Fornecido pelo proprietário/possuidor" if fonte_padrao == FONTE_AUTOR else "Ex.: GEOSANJA — Prefeitura de SJC"
        fonte = fonte_padrao if usar_padrao else st.text_input("Fonte", key=f"{chave}_fonte_txt", placeholder=exemplo)

        data_atual = st.checkbox("Data atual", value=cat["data_atual_padrao"], key=f"{chave}_hoje")
        data = HOJE if data_atual else st.date_input("Data da imagem", value=HOJE, key=f"{chave}_data", format="DD/MM/YYYY")
    return {"arquivo": arquivo, "fonte": fonte, "data": data}


def _bloco_categoria(chave: str, cat: dict) -> list:
    arquivos = st.file_uploader(
        "Fotos (pode selecionar mais de uma)",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key=f"{chave}_upload",
    )
    itens = []
    for i, arquivo in enumerate(arquivos or []):
        st.markdown(f"**Foto {i + 1}** — {arquivo.name}")
        itens.append(_controles_foto(f"{chave}_{i}", arquivo, cat))
        st.divider()
    return itens


categorias = []
for cat in CATEGORIAS_FOTO:
    with st.expander(cat["titulo"]):
        itens = _bloco_categoria(cat["codigo"], cat)
    categorias.append({"codigo": cat["codigo"], "titulo": cat["titulo"], "itens": itens})

# --- Fotos diversas (categorias criadas pelo profissional) -----------------
if "n_diversas" not in st.session_state:
    st.session_state.n_diversas = 0
b1, b2, _ = st.columns([1, 1, 3])
if b1.button("➕ Adicionar categoria"):
    st.session_state.n_diversas += 1
if b2.button("➖ Remover última", disabled=st.session_state.n_diversas == 0):
    st.session_state.n_diversas -= 1

CAT_LIVRE = {"codigo": CODIGO_DIVERSAS, "data_atual_padrao": True}
for k in range(st.session_state.n_diversas):
    with st.expander(f"Categoria adicional {k + 1}", expanded=True):
        nome = st.text_input("Nome da categoria", key=f"dv{k}_nome", placeholder="Ex.: FOTO DO MURO FRONTAL")
        itens = _bloco_categoria(f"dv{k}", CAT_LIVRE)
    categorias.append({"codigo": CODIGO_DIVERSAS, "titulo": (nome or f"FOTOS DIVERSAS {k + 1}").upper(), "itens": itens})

# --------------------------------------------------------------------------
# 4. Geração do PDF
# --------------------------------------------------------------------------
st.subheader("7. Gerar documento")

faltando = [
    CAMPOS_IDENTIFICACAO[k]
    for k in ("endereco", "inscricao_imobiliaria", "responsavel_tecnico", "crea_cau", "art_rrt",
              "proprietario", "cpf_cnpj_prop")
    if not dados.get(k)
]
sem_fonte = [
    f"{cat['titulo']} (foto {i + 1})"
    for cat in categorias for i, it in enumerate(cat["itens"]) if not it["fonte"]
]
if faltando:
    st.warning("Preencha ao menos: " + ", ".join(faltando))
if sem_fonte:
    st.warning("Informe a fonte de: " + "; ".join(sem_fonte))
if not declaracao_confirmada:
    st.info("A declaração do item 5 precisa ser confirmada para gerar o laudo.")

if dados.get("cpf_cnpj_prop") and not tipo_doc_prop:
    st.warning("CPF/CNPJ do proprietário inválido.")

pode_gerar = (not faltando and not sem_fonte and declaracao_confirmada
              and bool(tipo_doc_prop))
if st.button("Gerar PDF", type="primary", disabled=not pode_gerar):
    with st.spinner("Gerando PDF..."):
        resultado = gerar_pdf(dados, categorias)
    st.success(
        f"PDF gerado ({resultado['paginas']} páginas, laudo {resultado['doc_id']}, "
        f"{resultado['gerado_em']:%d/%m/%Y %H:%M}). Baixe, assine (eletronicamente ou à mão) "
        "e protocole junto ao processo."
    )
    nome_arquivo = f"laudo_{(dados.get('inscricao_imobiliaria') or 'sem_inscricao').replace('.', '')}_{resultado['doc_id']}.pdf"
    st.download_button("Baixar laudo em PDF", data=resultado["pdf"], file_name=nome_arquivo, mime="application/pdf")
