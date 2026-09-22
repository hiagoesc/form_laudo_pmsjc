# Laudo de vistoria padrão — formulário público (DGOP/PMSJC)

Formulário em Streamlit para o responsável técnico preencher os dados do laudo
de vistoria para fins de Regularização / Atestado de Regularidade da Construção,
anexar as fotos e gerar o **PDF padronizado**, já com **QR Codes** que devolvem
os dados estruturados na hora da análise.

**Não há banco de dados nem envio de dados à Prefeitura.** Tudo roda na sessão do
navegador de quem preenche; o PDF é a única saída. O documento deve ser assinado
eletronicamente (preferencialmente via gov.br) ou impresso, assinado à mão e
escaneado, para protocolo junto ao processo. Quando esse laudo chegar à análise,
os QR Codes permitem recuperar os dados sem depender de OCR sobre o documento
escaneado.

## Arquivos

| arquivo | papel |
|---|---|
| `app.py` | formulário (interface Streamlit) |
| `pdf_generator.py` | montagem do PDF, geração dos QR Codes, listas de uso/atividades, validação de CPF/CNPJ |
| `requirements.txt` | dependências do formulário |
| `.streamlit/config.toml` | tema claro (opcional, mas recomendado — ver abaixo) |
| `leitor_qr_laudo.ipynb` | notebook de leitura dos QR Codes (uso interno, **não** vai para o deploy) |
| `requirements_leitor.txt` | dependências do notebook (uso interno, **não** vai para o deploy) |

## Rodar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Tema claro

O Streamlit segue o tema do sistema operacional, então o formulário aparece
escuro para quem usa modo escuro. Para fixar o fundo branco, crie na raiz do
projeto a pasta `.streamlit` com o arquivo `config.toml`:

```toml
[theme]
base = "light"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"   # fundo dos campos e expanders
textColor = "#31333F"
```

Pastas iniciadas com ponto costumam ficar ocultas no Windows Explorer — confira
se ela entrou no commit, senão o deploy sai com o tema padrão.

## Deploy gratuito — Streamlit Community Cloud

Como o app não tem banco nem estado entre sessões, o [Streamlit Community
Cloud](https://streamlit.io/cloud) atende sem custo:

1. Suba para um repositório no GitHub: `app.py`, `pdf_generator.py`,
   `requirements.txt` e a pasta `.streamlit/`.
2. Em share.streamlit.io, conecte a conta do GitHub e aponte para o repositório
   e para o arquivo `app.py`.
3. O deploy gera uma URL pública (`https://<algo>.streamlit.app`) — é esse link
   que se distribui aos profissionais.
4. Domínio próprio (`laudo.sjc.sp.gov.br`, por exemplo) exige plano pago do
   Streamlit Cloud ou redirecionamento a partir de um domínio já controlado pela
   Prefeitura — pode ficar para depois de validar o fluxo.

Observações para o deploy:

- O repositório pode ser privado; o app publicado continua público.
- Apps gratuitos hibernam após alguns dias sem acesso e levam alguns segundos
  para "acordar" no primeiro acesso seguinte.
- Fotos anexadas ficam apenas em memória durante a sessão. O limite padrão de
  upload é 200 MB por arquivo; fotos de celular ficam bem abaixo disso, e o
  `pdf_generator` ainda reduz cada imagem para 1600 px no maior lado (acima de
  300 dpi na caixa de 13 cm) para não inflar o PDF.

## QR Codes (payload v2 — blocos)

Só vai para os QR Codes o que é conferido por código; endereço, quadra, lote,
bairro, telefones, e-mails e o nome do responsável técnico ficam apenas
impressos. JSON compacto, UTF-8, correção de erro nível Q, 3 cm cada, a 2 cm das
bordas (fora da faixa do carimbo do SIPEX).

| bloco `b` | onde | campos |
|---|---|---|
| `pg` | todas as páginas | `d` código do laudo, `ts` data/hora (America/Sao_Paulo), `p`/`n` página/total |
| `imo` | página 1 | `ins` inscrição imobiliária |
| `rt` | página 1 | `f` formação (`eng`/`arq`/`tec`), `reg` registro no conselho, `art` ART/RRT/TRT |
| `prop` | página 1 | `nm` nome, `cpf` **ou** `cnpj` (só dígitos, validados no formulário) |
| `meta` | página 1 | `uso` sigla da categoria, `atv` posição da atividade na lista (`"03"`), `cat` categorias de foto com anexo |

Todos os blocos têm `v` (versão = 2) e `d`, para o leitor juntar os pedaços do
mesmo laudo. O bloco `pg` em todas as páginas é o que permite delimitar onde o
laudo começa e termina dentro do processo digitalizado.

**`atv` depende da ordem de `ATIVIDADES_CS` em `pdf_generator.py`** — nunca
reordenar nem remover itens; atividade nova entra no final. Se a lista precisar
ser reorganizada, suba `VERSAO_PAYLOAD` e mantenha a lista antiga no leitor.
`atividade_por_codigo(sigla, "03")` faz a tradução inversa.

Tamanhos típicos: `imo` ~60 bytes, `rt` ~85, `meta` ~90, `pg` ~75, `prop` ~90–130
(depende do nome — é o bloco mais sensível à degradação de scan).

Leitura: `leitor_qr_laudo.ipynb` (lê vários QR Codes por página, agrupa por `d` e
confere páginas e blocos).

## Notas de implementação

- **Fonte das fotos:** cada categoria em `CATEGORIAS_FOTO` pode trazer
  `fonte_padrao`; sem essa chave, o padrão é "Elaborado pelo autor". Hoje as
  imagens aéreas usam "Google Earth" e a fachada de 6 anos atrás, "Google Street
  View". Desmarcando o check, o profissional digita outra fonte.
- **Expoentes:** as fontes padrão do reportlab (Helvetica) não têm os glifos ² e
  ³ — eles somem do PDF impresso, embora continuem no texto extraível. Por isso
  `_expoentes()` converte para `<super>`, sem depender de fonte externa. Se algum
  dia outros símbolos entrarem nos textos das atividades, vale conferir se
  aparecem no PDF renderizado.
- **Total de páginas:** o PDF é montado duas vezes, porque o `n` dos QR Codes só
  é conhecido depois de saber quantas páginas o laudo tem.

## Próximos ajustes possíveis

- Validação de tamanho/proporção mínima das fotos antes de aceitar o upload.
- Campo de observações livre por item da declaração (hoje é confirmação única).
- Se um dia existir `processo_id` conhecido no momento do preenchimento, o
  payload pode encolher para um ponteiro (`{processo_id, checksum}`) em vez dos
  dados crus.
