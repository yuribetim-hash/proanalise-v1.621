import streamlit as st
import os
import json
from io import BytesIO
from datetime import datetime, timedelta
from docxtpl import DocxTemplate, RichText
import hashlib
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

st.set_page_config(
    page_title="Proanalise v1.62",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# CONFIGURAÇÕES INICIAIS
# ============================================
if "tema_mode" not in st.session_state:
    st.session_state["tema_mode"] = "claro"
if "ultimo_backup" not in st.session_state:
    st.session_state["ultimo_backup"] = datetime.now()
if "marcadas_revisao" not in st.session_state:
    st.session_state["marcadas_revisao"] = set()
if "anotacoes_pessoais" not in st.session_state:
    st.session_state["anotacoes_pessoais"] = {}

HASH_SALT = "Proanalise_salt_2024"

# ============================================
# FUNÇÕES DE BACKUP
# ============================================
def fazer_backup_automatico():
    agora = datetime.now()
    diff = (agora - st.session_state["ultimo_backup"]).total_seconds()
    
    if diff >= 300:
        pasta_backup = os.path.join("dados", "backups")
        os.makedirs(pasta_backup, exist_ok=True)
        
        timestamp = agora.strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(pasta_backup, f"backup_{timestamp}.json")
        
        dados_backup = {
            "protocolo": st.session_state.get("protocolo", ""),
            "respostas_analise": st.session_state.get("respostas_analise", {}),
            "observacoes_analise": st.session_state.get("observacoes_analise", {}),
            "pendencias_analise": st.session_state.get("pendencias_analise", {}),
            "etapa": st.session_state.get("etapa", ""),
            "marcadas_revisao": list(st.session_state.get("marcadas_revisao", set())),
            "anotacoes_pessoais": st.session_state.get("anotacoes_pessoais", {}),
            "data_backup": timestamp
        }
        
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(dados_backup, f, indent=4, ensure_ascii=False)
        
        backups = sorted([f for f in os.listdir(pasta_backup) if f.startswith("backup_")])
        if len(backups) > 10:
            for old_backup in backups[:-10]:
                os.remove(os.path.join(pasta_backup, old_backup))
        
        st.session_state["ultimo_backup"] = agora
        return True
    return False

def restaurar_backup():
    pasta_backup = os.path.join("dados", "backups")
    if not os.path.exists(pasta_backup):
        return None
    
    backups = sorted([f for f in os.listdir(pasta_backup) if f.startswith("backup_")], reverse=True)
    if not backups:
        return None
    
    opcoes = {}
    for b in backups[:10]:
        data_str = b.replace("backup_", "").replace(".json", "")
        data_obj = datetime.strptime(data_str, "%Y%m%d_%H%M%S")
        opcoes[b] = data_obj.strftime("%d/%m/%Y %H:%M:%S")
    
    return opcoes

# ============================================
# FUNÇÕES DE PERMISSÕES E USUÁRIOS
# ============================================
def carregar_usuarios(caminho="usuarios.txt"):
    """Carrega usuários com níveis de permissão"""
    if not os.path.exists(caminho):
        st.error("Arquivo usuarios.txt não encontrado.")
        st.stop()
    
    usuarios = {}
    with open(caminho, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            partes = linha.split(";")
            if len(partes) >= 4:
                usuario, senha, papel, nivel = partes[0], partes[1], partes[2], partes[3]
                usuarios[usuario.strip()] = {
                    "senha": senha.strip(),
                    "papel": papel.strip(),
                    "nivel": int(nivel.strip())
                }
            elif len(partes) == 3:
                usuario, senha, papel = partes
                usuarios[usuario.strip()] = {
                    "senha": senha.strip(),
                    "papel": papel.strip(),
                    "nivel": 2 if "Sênior" in papel else 1
                }
            else:
                usuario, senha = partes[0], partes[1]
                usuarios[usuario.strip()] = {
                    "senha": senha.strip(),
                    "papel": "Analista",
                    "nivel": 2
                }
    return usuarios

def tem_permissao(nivel_necessario):
    """Verifica se o usuário logado tem permissão para a ação"""
    if "usuario_info" not in st.session_state:
        return False
    return st.session_state["usuario_info"]["nivel"] >= nivel_necessario

def pode_ver_menu(menu_item):
    """Verifica se o usuário pode ver um item do menu"""
    niveis_necessarios = {
        "1. Protocolo": 1,
        "2. Analista": 1,
        "3. Análise": 1,
        "4. Revisão": 1,
        "5. Gerar parecer": 1,
        "6. Dashboard": 2,
        "7. Comparador": 3
    }
    return tem_permissao(niveis_necessarios.get(menu_item, 1))

# ============================================
# FUNÇÕES DE MÚLTIPLOS ANALISTAS
# ============================================
def get_pasta_protocolo(protocolo):
    protocolo_limpo = protocolo.replace("/", "-").strip()
    return os.path.join("dados", protocolo_limpo)

def salvar_analise_analista(protocolo, analista, papel, respostas, observacoes, pendencias):
    pasta = get_pasta_protocolo(protocolo)
    os.makedirs(pasta, exist_ok=True)
    
    analista_hash = hashlib.md5(f"{analista}_{papel}_{HASH_SALT}".encode()).hexdigest()[:8]
    
    arquivo = os.path.join(pasta, f"analise_{analista_hash}_{papel}.json")
    registro = {
        "protocolo": protocolo,
        "analista": analista,
        "papel": papel,
        "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "respostas": respostas,
        "observacoes": observacoes,
        "pendencias": pendencias,
        "hash": analista_hash
    }
    
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(registro, f, indent=4, ensure_ascii=False)
    
    return analista_hash

def carregar_analises_analistas(protocolo):
    pasta = get_pasta_protocolo(protocolo)
    if not os.path.exists(pasta):
        return []
    
    analises = []
    for arquivo in os.listdir(pasta):
        if arquivo.startswith("analise_") and arquivo.endswith(".json"):
            with open(os.path.join(pasta, arquivo), "r", encoding="utf-8") as f:
                analises.append(json.load(f))
    
    return analises

def comparar_analises(analises):
    if len(analises) < 2:
        return None
    
    resultado = {
        "total_diferencas": 0,
        "diferencas_por_pergunta": {},
        "analistas": [a["analista"] for a in analises],
        "papeis": [a["papel"] for a in analises],
        "data_analises": [a["data"] for a in analises]
    }
    
    todas_perguntas = set()
    for analise in analises:
        todas_perguntas.update(analise["respostas"].keys())
    
    for pergunta in todas_perguntas:
        respostas_analistas = {}
        for analise in analises:
            resp = analise["respostas"].get(pergunta, "Não respondida")
            respostas_analistas[analise["analista"]] = resp
        
        valores_unicos = set(respostas_analistas.values())
        if len(valores_unicos) > 1:
            resultado["diferencas_por_pergunta"][pergunta] = respostas_analistas
            resultado["total_diferencas"] += 1
    
    return resultado

def render_comparador_analises(protocolo_atual):
    if not tem_permissao(3):
        st.error("❌ Acesso negado! Apenas Analistas Responsáveis podem acessar o Comparador.")
        return
    
    st.subheader("🔍 Comparador de Análises")
    
    analises = carregar_analises_analistas(protocolo_atual)
    
    if not analises:
        st.info("Nenhuma análise de outro analista encontrada para este protocolo.")
        return
    
    st.write(f"**Total de análises encontradas:** {len(analises)}")
    
    for a in analises:
        st.write(f"- {a['analista']} ({a['papel']}) - {a['data']}")
    
    if st.button("Comparar Análises", use_container_width=True):
        comparacao = comparar_analises(analises)
        
        if comparacao and comparacao["total_diferencas"] > 0:
            st.warning(f"⚠️ **{comparacao['total_diferencas']} divergências encontradas**")
            
            for pergunta, respostas in comparacao["diferencas_por_pergunta"].items():
                with st.expander(f"📌 Pergunta ID: {pergunta}"):
                    for analista, resposta in respostas.items():
                        st.write(f"**{analista}:** {resposta}")
        else:
            st.success("✅ Todas as análises estão consistentes!")

# ============================================
# FUNÇÕES DE MÉTRICAS
# ============================================
def calcular_tempo_medio_analise():
    pasta_dados = "dados"
    if not os.path.exists(pasta_dados):
        return None
    
    tempos = []
    for protocolo_dir in os.listdir(pasta_dados):
        protocolo_path = os.path.join(pasta_dados, protocolo_dir)
        if os.path.isdir(protocolo_path):
            analises = [f for f in os.listdir(protocolo_path) if f.startswith("AN") and f.endswith(".json")]
            if len(analises) >= 2:
                analises.sort()
                primeira = analises[0]
                ultima = analises[-1]
                
                with open(os.path.join(protocolo_path, primeira), "r", encoding="utf-8") as f:
                    data_primeira = datetime.strptime(json.load(f)["data"], "%d/%m/%Y")
                with open(os.path.join(protocolo_path, ultima), "r", encoding="utf-8") as f:
                    data_ultima = datetime.strptime(json.load(f)["data"], "%d/%m/%Y")
                
                tempo = (data_ultima - data_primeira).days
                tempos.append(tempo)
    
    if tempos:
        return sum(tempos) / len(tempos)
    return None

def gerar_grafico_inconformidades(respostas, grupos_inconformes):
    if not grupos_inconformes:
        return None
    
    dados = []
    for grupo, itens in grupos_inconformes.items():
        dados.append({"Grupo": grupo, "Inconformidades": len(itens)})
    
    df = pd.DataFrame(dados)
    fig = px.bar(df, x="Grupo", y="Inconformidades", 
                 title="Inconformidades por Grupo",
                 color="Inconformidades",
                 color_continuous_scale="Reds")
    
    fig.update_layout(
        xaxis_title="Grupo",
        yaxis_title="Número de Inconformidades",
        showlegend=False,
        height=400
    )
    
    return fig

def gerar_grafico_tempo_analises():
    pasta_dados = "dados"
    if not os.path.exists(pasta_dados):
        return None
    
    dados_tempo = []
    for protocolo_dir in os.listdir(pasta_dados):
        protocolo_path = os.path.join(pasta_dados, protocolo_dir)
        if os.path.isdir(protocolo_path):
            analises = [f for f in os.listdir(protocolo_path) if f.startswith("AN") and f.endswith(".json")]
            if analises:
                with open(os.path.join(protocolo_path, analises[0]), "r", encoding="utf-8") as f:
                    primeira = json.load(f)
                with open(os.path.join(protocolo_path, analises[-1]), "r", encoding="utf-8") as f:
                    ultima = json.load(f)
                
                data_inicio = datetime.strptime(primeira["data"], "%d/%m/%Y")
                data_fim = datetime.strptime(ultima["data"], "%d/%m/%Y")
                dias = (data_fim - data_inicio).days
                
                dados_tempo.append({
                    "Protocolo": protocolo_dir.replace("-", "/"),
                    "Dias de Análise": dias,
                    "Conclusão": ultima.get("conclusao", "Em análise")
                })
    
    if dados_tempo:
        df = pd.DataFrame(dados_tempo)
        fig = px.bar(df, x="Protocolo", y="Dias de Análise", 
                     title="Tempo de Análise por Protocolo",
                     color="Conclusão",
                     color_discrete_map={"FAVORÁVEL": "green", "DESFAVORÁVEL": "red"})
        fig.update_layout(xaxis_tickangle=-45, height=400)
        return fig
    return None

# ============================================
# FUNÇÕES DE BUSCA E FILTROS
# ============================================
def buscar_protocolos(termo_busca, filtro_status=None, filtro_analista=None, data_inicio=None, data_fim=None):
    pasta_dados = "dados"
    if not os.path.exists(pasta_dados):
        return []
    
    resultados = []
    for protocolo_dir in os.listdir(pasta_dados):
        protocolo_path = os.path.join(pasta_dados, protocolo_dir)
        if os.path.isdir(protocolo_path):
            if termo_busca.lower() in protocolo_dir.lower():
                status = "Em análise"
                analista = "Não informado"
                data_analise = datetime.fromtimestamp(os.path.getmtime(protocolo_path))
                
                analises = [f for f in os.listdir(protocolo_path) if f.startswith("AN") and f.endswith(".json")]
                if analises:
                    ultima = sorted(analises)[-1]
                    with open(os.path.join(protocolo_path, ultima), "r", encoding="utf-8") as f:
                        dados = json.load(f)
                        status = dados.get("conclusao", "Em análise")
                        analista = dados.get("analista", "Não informado")
                
                if filtro_status and filtro_status != "Todos":
                    if status != filtro_status:
                        continue
                if filtro_analista and filtro_analista != "Todos":
                    if analista != filtro_analista:
                        continue
                if data_inicio:
                    if data_analise.date() < data_inicio:
                        continue
                if data_fim:
                    if data_analise.date() > data_fim:
                        continue
                
                resultados.append({
                    "protocolo": protocolo_dir.replace("-", "/"),
                    "status": status,
                    "analista": analista,
                    "data_ultima": data_analise.strftime("%d/%m/%Y"),
                    "qtd_analises": len(analises)
                })
    
    return resultados

# ============================================
# FUNÇÕES DE PRODUTIVIDADE
# ============================================
def proxima_pergunta_nao_respondida(respostas, perguntas):
    for idx, p in enumerate(perguntas):
        resposta = respostas.get(p["id"])
        if resposta in ("", None, "Selecione..."):
            return p["id"], idx
    return None, None

# ============================================
# FUNÇÕES AUXILIARES
# ============================================
def resposta_preenchida(valor):
    return valor not in ("", None, "Selecione...")

def inicializar_estados():
    if "dados_antigos" not in st.session_state:
        st.session_state["dados_antigos"] = None
    if "etapa" not in st.session_state:
        st.session_state["etapa"] = "1. Protocolo"
    if "protocolo" not in st.session_state:
        st.session_state["protocolo"] = ""
    if "tipo" not in st.session_state:
        st.session_state["tipo"] = "Loteamento"
    if "interessado" not in st.session_state:
        st.session_state["interessado"] = ""
    if "n_lotes" not in st.session_state:
        st.session_state["n_lotes"] = 1
    if "matriculas" not in st.session_state:
        st.session_state["matriculas"] = ""
    if "analista" not in st.session_state:
        st.session_state["analista"] = ""
    if "matricula_analista" not in st.session_state:
        st.session_state["matricula_analista"] = ""
    if "setor" not in st.session_state:
        st.session_state["setor"] = ""
    if "n_analise" not in st.session_state:
        st.session_state["n_analise"] = ""
    if "pendencias_manuais" not in st.session_state:
        st.session_state["pendencias_manuais"] = {}
    if "respostas_temp" not in st.session_state:
        st.session_state["respostas_temp"] = {}
    if "observacoes_temp" not in st.session_state:
        st.session_state["observacoes_temp"] = {}
    if "respostas_analise" not in st.session_state:
        st.session_state["respostas_analise"] = {}
    if "observacoes_analise" not in st.session_state:
        st.session_state["observacoes_analise"] = {}
    if "pendencias_analise" not in st.session_state:
        st.session_state["pendencias_analise"] = {}

# ============================================
# CARREGAR TEMA (CLARO/ESCURO)
# ============================================
def carregar_tema():
    tema_claro = {
        "cores": {
            "primaria": "#0a2a3a",
            "primaria_clara": "#1a5276",
            "primaria_muito_escura": "#051a24",
            "secundaria": "#2c6b96",
            "sucesso": "#0d6e2e",
            "erro": "#b42318",
            "alerta": "#b54708",
            "info": "#175cd3",
            "fundo_claro": "#f8fafd",
            "fundo_branco": "#ffffff",
            "texto_principal": "#1a1a1a",
            "texto_secundario": "#2c3e50",
            "texto_caption": "#666666",
            "texto_titulo": "#051a24",
            "fundo_app": "linear-gradient(135deg, #e8f0fe 0%, #d4e4fc 100%)",
            "sidebar_fundo": "linear-gradient(180deg, #0a2a3a 0%, #051a24 100%)"
        },
        "botoes": {
            "primario_fundo": "#0d6e2e",
            "primario_fundo_hover": "#0f8a3a",
            "secundario_fundo": "#0a2a3a",
            "secundario_fundo_hover": "#1a5276",
            "texto": "#ffffff"
        },
        "status": {
            "conforme": {"fundo": "#ecfdf3", "borda": "#067647", "texto": "#067647", "icone": "✅"},
            "inconforme": {"fundo": "#fef3f2", "borda": "#b42318", "texto": "#7a271a", "icone": "⛔"},
            "pendente": {"fundo": "#fffaeb", "borda": "#b54708", "texto": "#7a4a0a", "icone": "⏳"},
            "nao_se_enquadra": {"fundo": "#eff6ff", "borda": "#175cd3", "texto": "#0e4a8a", "icone": "ℹ️"}
        }
    }
    
    tema_escuro = {
        "cores": {
            "primaria": "#e8f0fe",
            "primaria_clara": "#d4e4fc",
            "primaria_muito_escura": "#c5d5e6",
            "secundaria": "#2c6b96",
            "sucesso": "#0f8a3a",
            "erro": "#f5c2c7",
            "alerta": "#fedf89",
            "info": "#c7d7fe",
            "fundo_claro": "#1e1e2e",
            "fundo_branco": "#2a2a3e",
            "texto_principal": "#e0e0e0",
            "texto_secundario": "#b0b0b0",
            "texto_caption": "#888888",
            "texto_titulo": "#ffffff",
            "fundo_app": "linear-gradient(135deg, #1a1a2e 0%, #0a0a15 100%)",
            "sidebar_fundo": "linear-gradient(180deg, #0a0a15 0%, #05050a 100%)"
        },
        "botoes": {
            "primario_fundo": "#0f8a3a",
            "primario_fundo_hover": "#0d6e2e",
            "secundario_fundo": "#2c6b96",
            "secundario_fundo_hover": "#1a5276",
            "texto": "#ffffff"
        },
        "status": {
            "conforme": {"fundo": "#1a3a2a", "borda": "#0f8a3a", "texto": "#90ee90", "icone": "✅"},
            "inconforme": {"fundo": "#3a1a1a", "borda": "#f5c2c7", "texto": "#f5c2c7", "icone": "⛔"},
            "pendente": {"fundo": "#3a2a1a", "borda": "#fedf89", "texto": "#fedf89", "icone": "⏳"},
            "nao_se_enquadra": {"fundo": "#1a2a3a", "borda": "#c7d7fe", "texto": "#c7d7fe", "icone": "ℹ️"}
        }
    }
    
    if st.session_state.get("tema_mode") == "escuro":
        return tema_escuro
    return tema_claro

# ============================================
# RENDERIZAÇÃO DO TEMA CSS
# ============================================
tema = carregar_tema()

css_tema = f"""
<style>
    .stApp {{ background: {tema["cores"]["fundo_app"]}; }}
    .main > div {{ background-color: {tema["cores"]["fundo_branco"]}; border-radius: 12px; padding: 1rem; }}
    
    [data-testid="stSidebar"] {{ background: {tema["cores"]["sidebar_fundo"]}; }}
    [data-testid="stSidebar"] * {{ color: {tema["botoes"]["texto"]} !important; }}
    
    h1 {{ color: {tema["cores"]["texto_titulo"]} !important; font-weight: 700 !important; font-size: 24px !important; }}
    h2, h3, h4 {{ color: {tema["cores"]["primaria"]} !important; font-weight: 600 !important; }}
    
    /* Caption - texto abaixo do título */
    .stCaption {{
        color: {tema["cores"].get("texto_caption", tema["cores"]["texto_secundario"])} !important;
        font-size: 14px !important;
    }}
    
    .stTextInput input, .stTextArea textarea, .stNumberInput input {{
        background-color: {tema["cores"]["fundo_branco"]} !important;
        color: {tema["cores"]["texto_principal"]} !important;
        border: 1px solid {tema["cores"]["primaria_clara"]} !important;
        border-radius: 6px !important;
    }}
    
    .stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {{
        border-color: {tema["cores"]["primaria"]} !important;
        box-shadow: 0 0 0 2px rgba(26, 82, 118, 0.2) !important;
    }}
    
    .stTextInput label, .stSelectbox label, .stTextArea label, .stNumberInput label {{
        color: {tema["cores"]["primaria_clara"]} !important;
        font-weight: 600 !important;
    }}
    
    .stSelectbox select {{
        background-color: {tema["cores"]["fundo_branco"]} !important;
        color: {tema["cores"]["texto_principal"]} !important;
        border: 1px solid {tema["cores"]["primaria_clara"]} !important;
        border-radius: 6px !important;
        font-size: 14px !important;
    }}
    
    /* DROPDOWN - Janela que abre */
    div[data-baseweb="menu"] {{
        background-color: #1a1a2e !important;
        border: 1px solid #2c6b96 !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3) !important;
    }}
    
    div[data-baseweb="menu"] div {{
        background-color: #1a1a2e !important;
        color: white !important;
        padding: 8px 16px !important;
        font-size: 14px !important;
        cursor: pointer !important;
    }}
    
    div[data-baseweb="menu"] div:hover {{
        background-color: #2c6b96 !important;
        color: white !important;
    }}
    
    div[data-baseweb="menu"] div[aria-selected="true"] {{
        background-color: #0d6e2e !important;
        color: white !important;
    }}
    
    /* BOTÕES */
    .stButton > button {{
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        color: {tema["botoes"]["texto"]} !important;
        border: none !important;
        transition: all 0.3s ease !important;
    }}
    
    .stButton > button[kind="primary"] {{
        background-color: {tema["botoes"]["primario_fundo"]} !important;
    }}
    
    .stButton > button[kind="primary"]:hover {{
        background-color: {tema["botoes"]["primario_fundo_hover"]} !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }}
    
    .stButton > button:not([kind="primary"]) {{
        background-color: {tema["botoes"]["secundario_fundo"]} !important;
    }}
    
    .stButton > button:not([kind="primary"]):hover {{
        background-color: {tema["botoes"]["secundario_fundo_hover"]} !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }}
    
    .stButton > button:disabled {{
        background-color: #cccccc !important;
        color: #666666 !important;
    }}
    
    .stDownloadButton button {{
        background-color: {tema["botoes"]["primario_fundo"]} !important;
    }}
    
    /* STATUS BADGES */
    .status-badge-conforme {{
        background-color: {tema["status"]["conforme"]["fundo"]};
        border-left: 4px solid {tema["status"]["conforme"]["borda"]};
        padding: 8px 12px;
        border-radius: 6px;
        margin-top: 28px;
        color: {tema["status"]["conforme"]["texto"]};
        font-weight: 600;
    }}
    
    .status-badge-inconforme {{
        background-color: {tema["status"]["inconforme"]["fundo"]};
        border-left: 4px solid {tema["status"]["inconforme"]["borda"]};
        padding: 8px 12px;
        border-radius: 6px;
        margin-top: 28px;
        color: {tema["status"]["inconforme"]["texto"]};
        font-weight: 600;
    }}
    
    .status-badge-pendente {{
        background-color: {tema["status"]["pendente"]["fundo"]};
        border-left: 4px solid {tema["status"]["pendente"]["borda"]};
        padding: 8px 12px;
        border-radius: 6px;
        margin-top: 28px;
        color: {tema["status"]["pendente"]["texto"]};
        font-weight: 600;
    }}
    
    .status-badge-na {{
        background-color: {tema["status"]["nao_se_enquadra"]["fundo"]};
        border-left: 4px solid {tema["status"]["nao_se_enquadra"]["borda"]};
        padding: 8px 12px;
        border-radius: 6px;
        margin-top: 28px;
        color: {tema["status"]["nao_se_enquadra"]["texto"]};
        font-weight: 600;
    }}
    
    /* PROGRESSO */
    .progress-wrap {{
        width: 100%;
        background: #e9ecef;
        border-radius: 999px;
        height: 14px;
        overflow: hidden;
        margin: 8px 0;
    }}
    
    .progress-bar {{
        height: 14px;
        border-radius: 999px;
        transition: width 0.3s ease;
    }}
    
    /* CARDS E MÉTRICAS */
    .card {{
        padding: 12px 16px;
        border: 1px solid #c5d5e6;
        border-radius: 10px;
        background: {tema["cores"]["fundo_claro"]};
        margin-bottom: 0.6rem;
        color: {tema["cores"]["texto_principal"]};
    }}
    
    [data-testid="stMetric"] {{
        background-color: {tema["cores"]["fundo_claro"]};
        border-radius: 8px;
        padding: 10px;
        border: 1px solid #c5d5e6;
    }}
    
    [data-testid="stMetric"] label {{
        color: {tema["cores"]["primaria"]} !important;
        font-weight: 600 !important;
    }}
    
    [data-testid="stMetric"] .stMetricValue {{
        color: {tema["cores"]["texto_principal"]} !important;
        font-weight: 700 !important;
    }}
    
    /* EXPANDERS */
    .streamlit-expanderHeader {{
        background-color: {tema["cores"]["fundo_claro"]} !important;
        color: {tema["cores"]["primaria"]} !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
    }}
    
    .streamlit-expanderContent {{
        background-color: {tema["cores"]["fundo_branco"]} !important;
        border-radius: 0 0 8px 8px !important;
    }}
    
    /* CARD DE REVISÃO */
    .card-revisao {{
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 8px 12px;
        border-radius: 6px;
        margin: 5px 0;
    }}
    
    /* TEXTOS GERAIS */
    p, li, .stMarkdown, .stText {{
        color: {tema["cores"]["texto_secundario"]};
    }}
    
    hr {{
        border-color: {tema["cores"]["primaria_clara"]};
    }}
    
    /* INFORMAÇÕES, SUCESSO, AVISOS, ERROS */
    .stInfo, .stSuccess, .stWarning, .stError {{
        border-radius: 8px !important;
    }}
</style>
"""
# ============================================
# JAVASCRIPT PARA O DROPDOWN
# ============================================
st.markdown("""
<script>
document.addEventListener('DOMContentLoaded', function() {
    function styleDropdowns() {
        const dropdowns = document.querySelectorAll('[data-baseweb="menu"]');
        dropdowns.forEach(dropdown => {
            dropdown.style.backgroundColor = '#1a1a2e';
            dropdown.style.border = '1px solid #2c6b96';
            dropdown.style.borderRadius = '8px';
            const options = dropdown.querySelectorAll('[role="option"]');
            options.forEach(option => {
                option.style.backgroundColor = '#1a1a2e';
                option.style.color = 'white';
                option.style.padding = '8px 16px';
                if (option.getAttribute('aria-selected') === 'true') {
                    option.style.backgroundColor = '#0d6e2e';
                }
                option.addEventListener('mouseenter', function() {
                    this.style.backgroundColor = '#2c6b96';
                });
                option.addEventListener('mouseleave', function() {
                    if (this.getAttribute('aria-selected') === 'true') {
                        this.style.backgroundColor = '#0d6e2e';
                    } else {
                        this.style.backgroundColor = '#1a1a2e';
                    }
                });
            });
        });
    }
    const observer = new MutationObserver(function() { styleDropdowns(); });
    observer.observe(document.body, { childList: true, subtree: true });
    styleDropdowns();
});
</script>
""", unsafe_allow_html=True)

# ============================================
# TELA DE LOGIN
# ============================================
def tela_login():
    col_logo1, col_logo2, col_logo3 = st.columns([1, 2, 1])
    with col_logo2:
        if os.path.exists("logo.png"):
            st.image("logo.png", width=200)
    
    st.title("📐 Proanalise v1.62")
    st.caption("Sistema de análise urbanística e geração de parecer técnico")
    
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("### Acesso ao sistema")
        usuarios = carregar_usuarios()
        
        user = st.text_input("Usuário", key="login_user")
        senha = st.text_input("Senha", type="password", key="login_senha")
        
        if st.button("Entrar", use_container_width=True, key="btn_login", type="primary"):
            if user in usuarios and usuarios[user]["senha"] == senha:
                st.session_state["logado"] = True
                st.session_state["usuario"] = user
                st.session_state["usuario_info"] = usuarios[user]
                st.session_state["papel"] = usuarios[user]["papel"]
                st.session_state["nivel"] = usuarios[user]["nivel"]
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    
   

if "logado" not in st.session_state:
    st.session_state["logado"] = False

if not st.session_state["logado"]:
    tela_login()
    st.stop()

# ============================================
# SIDEBAR
# ============================================
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", width=150)

st.sidebar.title("📐 Proanalise v1.62")
st.sidebar.write(f"👤 {st.session_state['usuario']} - {st.session_state.get('papel', 'Analista')}")
st.sidebar.write(f"🔒 Nível: {st.session_state.get('nivel', 1)}")

# Toggle de tema
tema_toggle = st.sidebar.toggle("🌙 Modo Escuro", value=(st.session_state["tema_mode"] == "escuro"))
if tema_toggle:
    st.session_state["tema_mode"] = "escuro"
else:
    st.session_state["tema_mode"] = "claro"

# Backup
if st.sidebar.button("💾 Backup Manual", use_container_width=True):
    if fazer_backup_automatico():
        st.sidebar.success("Backup realizado com sucesso!")

backups_disponiveis = restaurar_backup()
if backups_disponiveis and tem_permissao(2):
    with st.sidebar.expander("🔄 Restaurar Backup"):
        backup_selecionado = st.selectbox("Selecione o backup", list(backups_disponiveis.keys()),
                                          format_func=lambda x: backups_disponiveis[x])
        if st.button("Restaurar", use_container_width=True):
            caminho_backup = os.path.join("dados", "backups", backup_selecionado)
            with open(caminho_backup, "r", encoding="utf-8") as f:
                dados_restaurados = json.load(f)
                for key, value in dados_restaurados.items():
                    if key in st.session_state:
                        st.session_state[key] = value
            st.rerun()

st.sidebar.markdown("---")

# Busca rápida (apenas para nível 2+)
if tem_permissao(2):
    st.sidebar.subheader("🔍 Busca Rápida")
    termo_busca = st.sidebar.text_input("N° Protocolo", placeholder="Digite o protocolo...")
    if termo_busca:
        resultados = buscar_protocolos(termo_busca)
        if resultados:
            for r in resultados[:5]:
                st.sidebar.write(f"📋 {r['protocolo']} - {r['status']}")

st.sidebar.markdown("---")

if st.sidebar.button("🚪 Sair", use_container_width=True, key="btn_sair"):
    st.session_state["logado"] = False
    st.session_state.pop("dados_antigos", None)
    st.rerun()

# ============================================
# FUNÇÕES DE RENDERIZAÇÃO DE STATUS
# ============================================
def render_status_badge(status):
    if status == "conforme":
        st.markdown(f"<div class='status-badge-conforme'>{tema['status']['conforme']['icone']} <strong>CONFORME</strong></div>", unsafe_allow_html=True)
    elif status == "inconforme":
        st.markdown(f"<div class='status-badge-inconforme'>{tema['status']['inconforme']['icone']} <strong>INCONFORME</strong></div>", unsafe_allow_html=True)
    elif status == "pendente":
        st.markdown(f"<div class='status-badge-pendente'>{tema['status']['pendente']['icone']} <strong>PENDENTE</strong></div>", unsafe_allow_html=True)
    elif status == "na":
        st.markdown(f"<div class='status-badge-na'>{tema['status']['nao_se_enquadra']['icone']} <strong>NÃO SE ENQUADRA</strong></div>", unsafe_allow_html=True)

def cor_progresso(pct):
    r = int(255 * (1 - pct))
    g = int(180 * pct + 60)
    b = 60
    return f"rgb({r},{g},{b})"

def render_progresso(preenchidas, total, pct, destino):
    cor = cor_progresso(pct)
    html = f"""
    <div><b>{preenchidas}/{total}</b> respostas preenchidas ({int(pct*100)}%)</div>
    <div class="progress-wrap">
        <div class="progress-bar" style="width:{pct*100:.1f}%; background:{cor};"></div>
    </div>
    """
    destino.markdown(html, unsafe_allow_html=True)

# ============================================
# CARREGAR PERGUNTAS
# ============================================
def carregar_perguntas_txt(caminho="perguntas.txt"):
    if not os.path.exists(caminho):
        st.error("Arquivo perguntas.txt não encontrado.")
        st.stop()
    perguntas = []
    bloco = {}
    with open(caminho, "r", encoding="utf-8") as f:
        linhas = f.readlines()
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            if bloco:
                perguntas.append(bloco)
                bloco = {}
            continue
        if linha.startswith("GRUPO:"):
            bloco["grupo"] = linha.replace("GRUPO:", "").strip()
        elif linha.startswith("ID:"):
            bloco["id"] = linha.replace("ID:", "").strip()
        elif linha.startswith("PERGUNTA:"):
            bloco["pergunta"] = linha.replace("PERGUNTA:", "").strip()
        elif linha.startswith("OPCOES:"):
            bloco["opcoes"] = [op.strip() for op in linha.replace("OPCOES:", "").strip().split(";")]
        elif linha.startswith("CONFORMES:"):
            bloco["conformes"] = [op.strip() for op in linha.replace("CONFORMES:", "").strip().split(";")]
        elif linha.startswith("REGRA_"):
            chave, valor = linha.split(":", 1)
            resposta = chave.replace("REGRA_", "").strip()
            bloco.setdefault("regras", {})[resposta] = {"texto": valor.strip()}
    if bloco:
        perguntas.append(bloco)
    return perguntas

perguntas = carregar_perguntas_txt("perguntas.txt")
inicializar_estados()

# ============================================
# CABEÇALHO PRINCIPAL
# ============================================
col_logo, col_titulo = st.columns([1, 5])
with col_logo:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=100)
with col_titulo:
    st.title("📐 Proanalise v1.62")
    st.caption("Análise urbanística padronizada com geração de parecer técnico")

# ============================================
# NAVEGAÇÃO (com base nas permissões)
# ============================================
menus_base = ["1. Protocolo", "2. Analista", "3. Análise", "4. Revisão", "5. Gerar parecer"]
menus_nivel2 = ["6. Dashboard"]
menus_nivel3 = ["7. Comparador"]

menus_disponiveis = []
for menu in menus_base:
    if pode_ver_menu(menu):
        menus_disponiveis.append(menu)

if tem_permissao(2):
    menus_disponiveis.extend(menus_nivel2)

if tem_permissao(3):
    menus_disponiveis.extend(menus_nivel3)

etapa_atual = st.sidebar.radio("📋 Etapas", menus_disponiveis, 
                                index=menus_disponiveis.index(st.session_state["etapa"]) if st.session_state["etapa"] in menus_disponiveis else 0)
if etapa_atual != st.session_state["etapa"]:
    st.session_state["etapa"] = etapa_atual
    st.rerun()

# ============================================
# FUNÇÕES PRINCIPAIS (definir_conclusao, montar_inconformidades, etc)
# ============================================
def definir_conclusao(respostas, pendencias_manuais=None):
    for p in perguntas:
        resposta = respostas.get(p["id"])
        if not resposta_preenchida(resposta):
            continue
        conformes = p.get("conformes", ["Sim", "Não se enquadra"])
        if resposta not in conformes and resposta in p.get("regras", {}):
            return "DESFAVORÁVEL"
    if pendencias_manuais:
        for grupo, pendencias in pendencias_manuais.items():
            if isinstance(pendencias, list):
                for pendencia in pendencias:
                    if pendencia and pendencia.strip():
                        return "DESFAVORÁVEL"
            elif pendencias and pendencias.strip():
                return "DESFAVORÁVEL"
    return "FAVORÁVEL"

def montar_inconformidades_por_grupo(respostas, observacoes, pendencias_manuais=None):
    grupos = {}
    for p in perguntas:
        pid = p["id"]
        resp = respostas.get(pid)
        if not resposta_preenchida(resp):
            continue
        conformes = p.get("conformes", ["Sim", "Não se enquadra"])
        if resp not in conformes and resp in p.get("regras", {}):
            grupo = p["grupo"]
            texto = p["regras"][resp]["texto"]
            obs = observacoes.get(pid, "").strip()
            if obs:
                texto += f"\nObservação: {obs}"
            grupos.setdefault(grupo, []).append(texto)
    if pendencias_manuais:
        for grupo, pendencias in pendencias_manuais.items():
            if isinstance(pendencias, list):
                for pendencia in pendencias:
                    if pendencia and pendencia.strip():
                        grupos.setdefault(grupo, []).append(pendencia)
            elif pendencias and pendencias.strip():
                grupos.setdefault(grupo, []).append(pendencias)
    return grupos

def montar_inconformidades_rt(respostas, observacoes, pendencias_manuais=None):
    grupos = montar_inconformidades_por_grupo(respostas, observacoes, pendencias_manuais)
    rt = RichText()
    contador = 1
    if grupos:
        for grupo, itens in grupos.items():
            rt.add(grupo.upper(), bold=True)
            rt.add("\n\n")
            for item in itens:
                rt.add(f"{contador}. {item}")
                rt.add("\n\n")
                contador += 1
    else:
        rt.add("Não foram identificadas inconformidades.")
    return rt

def gerar_docx(dados, respostas, observacoes, conclusao, analista, matricula, setor, n_analise, pendencias_manuais=None):
    if not os.path.exists("modelo_parecer.docx"):
        st.error("Arquivo modelo_parecer.docx não encontrado.")
        st.stop()
    doc = DocxTemplate("modelo_parecer.docx")
    inconformidades_rt = montar_inconformidades_rt(respostas, observacoes, pendencias_manuais)
    matriculas_str = dados.get("matriculas", "")
    if isinstance(matriculas_str, list):
        matriculas_str = ", ".join(matriculas_str)
    context = {
        "protocolo": dados["protocolo"],
        "tipo": dados["tipo"],
        "interessado": dados["interessado"],
        "n_lotes": dados["n_lotes"],
        "matriculas": matriculas_str,
        "inconformidades": inconformidades_rt,
        "conclusao": conclusao,
        "data": f"Data: {datetime.now().strftime('%d/%m/%Y')}",
        "analista": f"Analista: {analista}",
        "matricula": matricula,
        "setor": setor,
        "n_analise": n_analise
    }
    doc.render(context)
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def progresso_percentual(respostas):
    total = len(perguntas)
    preenchidas = sum(1 for v in respostas.values() if resposta_preenchida(v))
    if total == 0:
        return 0, 0, 0.0
    pct = preenchidas / total
    return preenchidas, total, pct

def resumo_status_pergunta(p, resposta):
    if not resposta_preenchida(resposta):
        return "pendente"
    conformes = p.get("conformes", ["Sim", "Não se enquadra"])
    if resposta == "Não se enquadra":
        return "na"
    if resposta in conformes:
        return "conforme"
    if resposta in p.get("regras", {}):
        return "inconforme"
    return "neutro"

# ============================================
# ETAPA 1 - PROTOCOLO
# ============================================
if st.session_state["etapa"] == "1. Protocolo":
    st.header("📋 Dados do protocolo")
    
    protocolo = st.text_input("N° Protocolo", value=st.session_state["protocolo"], key="protocolo_input")
    if protocolo != st.session_state["protocolo"]:
        st.session_state["protocolo"] = protocolo

    if st.session_state["protocolo"]:
        ultima = None
        pasta = get_pasta_protocolo(st.session_state["protocolo"])
        if os.path.exists(pasta):
            analises = [f for f in os.listdir(pasta) if f.startswith("AN") and f.endswith(".json")]
            if analises:
                with open(os.path.join(pasta, sorted(analises)[-1]), "r", encoding="utf-8") as f:
                    ultima = json.load(f)
        
        if ultima:
            st.info(f"📋 Última análise encontrada: AN{ultima['n_analise']}")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("▶️ Continuar análise", use_container_width=True):
                    st.session_state["dados_antigos"] = ultima
                    st.session_state["tipo"] = ultima["dados"].get("tipo", "Loteamento")
                    st.session_state["interessado"] = ultima["dados"].get("interessado", "")
                    st.session_state["n_lotes"] = int(ultima["dados"].get("n_lotes", 1))
                    st.session_state["matriculas"] = ultima["dados"].get("matriculas", "")
                    st.session_state["etapa"] = "2. Analista"
                    st.rerun()
            with col_b:
                if st.button("➕ Iniciar nova análise", use_container_width=True):
                    st.session_state["dados_antigos"] = None
                    st.session_state["etapa"] = "2. Analista"
                    st.rerun()
        else:
            if st.button("Prosseguir →", use_container_width=True, type="primary"):
                if st.session_state["protocolo"]:
                    st.session_state["etapa"] = "2. Analista"
                    st.rerun()

    st.subheader("🏢 Dados do empreendimento")
    tipo = st.selectbox("Tipo do Empreendimento", ["Loteamento", "Condomínio fechado de lotes"], 
                        index=0 if st.session_state["tipo"] == "Loteamento" else 1, key="tipo_select")
    st.session_state["tipo"] = tipo
    interessado = st.text_input("Requerente", value=st.session_state["interessado"], key="interessado_input")
    st.session_state["interessado"] = interessado
    n_lotes = st.number_input("Número de Lotes", min_value=1, value=st.session_state["n_lotes"], key="n_lotes_input")
    st.session_state["n_lotes"] = n_lotes
    matriculas = st.text_area("Matrícula(s) do Empreendimento", value=st.session_state["matriculas"], 
                               key="matriculas_input", placeholder="Digite a(s) matrícula(s) separadas por vírgula")
    st.session_state["matriculas"] = matriculas

# ============================================
# ETAPA 2 - ANALISTA
# ============================================
elif st.session_state["etapa"] == "2. Analista":
    st.header("👤 Dados do analista")
    st.info(f"📌 Protocolo: **{st.session_state['protocolo']}**")
    
    analista = st.text_input("Nome do Analista", value=st.session_state["analista"], key="analista_input")
    st.session_state["analista"] = analista
    matricula_analista = st.text_input("Matrícula do Analista", value=st.session_state["matricula_analista"], key="matricula_analista_input")
    st.session_state["matricula_analista"] = matricula_analista
    setor = st.text_input("Setor", value=st.session_state["setor"], key="setor_input")
    st.session_state["setor"] = setor
    
    n_analise_sugerida = "1"
    if st.session_state["protocolo"]:
        pasta = get_pasta_protocolo(st.session_state["protocolo"])
        if os.path.exists(pasta):
            analises = [f for f in os.listdir(pasta) if f.startswith("AN") and f.endswith(".json")]
            if analises:
                ultimo_num = max([int(a.replace("AN", "").replace(".json", "")) for a in analises])
                n_analise_sugerida = str(ultimo_num + 1)
    
    if not st.session_state["n_analise"]:
        st.session_state["n_analise"] = n_analise_sugerida
    
    n_analise = st.text_input("Nº da Análise", value=st.session_state["n_analise"], key="n_analise_input")
    st.session_state["n_analise"] = n_analise
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Voltar", use_container_width=True):
            st.session_state["etapa"] = "1. Protocolo"
            st.rerun()
    with col2:
        if st.button("Prosseguir →", use_container_width=True, type="primary"):
            if st.session_state["analista"] and st.session_state["n_analise"]:
                st.session_state["etapa"] = "3. Análise"
                st.rerun()
            else:
                st.error("⚠️ Preencha todos os campos")

# ============================================
# ETAPA 3 - ANÁLISE
# ============================================
elif st.session_state["etapa"] == "3. Análise":
    st.header("🔍 Análise técnica")
    st.info(f"📌 Protocolo: **{st.session_state['protocolo']}** | Analista: **{st.session_state['analista']}**")
    
    fazer_backup_automatico()
    
    if "respostas_analise" not in st.session_state:
        st.session_state["respostas_analise"] = st.session_state.get("respostas_temp", {})
    if "observacoes_analise" not in st.session_state:
        st.session_state["observacoes_analise"] = st.session_state.get("observacoes_temp", {})
    if "pendencias_analise" not in st.session_state:
        st.session_state["pendencias_analise"] = st.session_state.get("pendencias_manuais", {})
    
    respostas = st.session_state["respostas_analise"]
    observacoes = st.session_state["observacoes_analise"]
    pendencias_manuais = st.session_state["pendencias_analise"]
    
    # Botão próximo não respondido
    proximo_id, proximo_idx = proxima_pergunta_nao_respondida(respostas, perguntas)
    if proximo_id:
        if st.button("🎯 Próxima pergunta não respondida", use_container_width=True):
            st.session_state["scroll_to"] = proximo_id
            st.rerun()
    
    # Campo de anotações pessoais
    with st.expander("📓 Anotações Pessoais (não vão para o parecer)"):
        anotacao_atual = st.session_state["anotacoes_pessoais"].get(st.session_state["protocolo"], "")
        nova_anotacao = st.text_area("Suas anotações", value=anotacao_atual, height=100)
        if nova_anotacao != anotacao_atual:
            st.session_state["anotacoes_pessoais"][st.session_state["protocolo"]] = nova_anotacao
    
    # Manter ordem do arquivo
    grupos_ordenados = []
    for p in perguntas:
        grupo = p["grupo"]
        if grupo not in grupos_ordenados:
            grupos_ordenados.append(grupo)
    
    inconformes_sidebar = []
    
    for grupo in grupos_ordenados:
        perguntas_grupo = [p for p in perguntas if p["grupo"] == grupo]
        with st.expander(f"📁 {grupo}", expanded=False):
            for idx, p in enumerate(perguntas_grupo):
                pid = p["id"]
                
                if st.session_state.get("scroll_to") == pid:
                    st.rerun()
                
                valor_salvo = respostas.get(pid, "Selecione...")
                obs_salva = observacoes.get(pid, "")
                
                if st.session_state["dados_antigos"] and pid not in respostas:
                    valor_salvo = st.session_state["dados_antigos"]["respostas"].get(pid, "Selecione...")
                    obs_salva = st.session_state["dados_antigos"]["observacoes"].get(pid, "")
                
                opcoes = ["Selecione..."] + p["opcoes"]
                idx_padrao = opcoes.index(valor_salvo) if valor_salvo in opcoes else 0
                
                col_pergunta, col_status, col_marcar = st.columns([3, 1, 0.5])
                
                with col_pergunta:
                    resposta = st.selectbox(p["pergunta"], opcoes, index=idx_padrao, key=f"resp_{pid}", help=f"ID: {pid}")
                    respostas[pid] = resposta
                
                with col_status:
                    status = resumo_status_pergunta(p, resposta)
                    render_status_badge(status)
                    if status == "inconforme":
                        inconformes_sidebar.append(p["pergunta"])
                
                with col_marcar:
                    marcada = pid in st.session_state["marcadas_revisao"]
                    if st.button("🔖", key=f"marcar_{pid}", help="Marcar para revisão"):
                        if marcada:
                            st.session_state["marcadas_revisao"].discard(pid)
                        else:
                            st.session_state["marcadas_revisao"].add(pid)
                        st.rerun()
                
                if pid in st.session_state["marcadas_revisao"]:
                    st.markdown("<div class='card-revisao'>🔖 Marcada para revisão posterior</div>", unsafe_allow_html=True)
                
                obs = st.text_area("📝 Observação (opcional)", value=obs_salva, key=f"obs_{pid}", height=68)
                observacoes[pid] = obs
                st.markdown("---")
            
            # Inconformidades Diversas
            st.markdown("### 📝 Inconformidades Diversas")
            
            if grupo not in pendencias_manuais:
                pendencias_manuais[grupo] = []
            
            if pendencias_manuais[grupo]:
                for i, pendencia in enumerate(pendencias_manuais[grupo]):
                    if pendencia:
                        col_p, col_b = st.columns([10, 1])
                        with col_p:
                            st.markdown(f"📌 {pendencia}")
                        with col_b:
                            if st.button("🗑️", key=f"del_{grupo}_{i}"):
                                pendencias_manuais[grupo].pop(i)
                                st.rerun()
            
            if st.button(f"+ Adicionar", key=f"add_{grupo}"):
                pendencias_manuais[grupo].append("")
                st.rerun()
            
            if pendencias_manuais[grupo] and not pendencias_manuais[grupo][-1]:
                nova = st.text_area("Nova inconformidade", key=f"new_{grupo}", height=68)
                if nova:
                    pendencias_manuais[grupo][-1] = nova
                    st.rerun()
    
    st.session_state["respostas_analise"] = respostas
    st.session_state["observacoes_analise"] = observacoes
    st.session_state["pendencias_analise"] = pendencias_manuais
    
    preenchidas, total, pct = progresso_percentual(respostas)
    render_progresso(preenchidas, total, pct, st)
    
    if preenchidas < total:
        st.warning(f"⚠️ Atenção: {total - preenchidas} perguntas ainda não foram respondidas!")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Voltar", use_container_width=True):
            st.session_state["etapa"] = "2. Analista"
            st.rerun()
    with col2:
        if st.button("Prosseguir →", use_container_width=True, type="primary"):
            if preenchidas == total:
                st.session_state["respostas_temp"] = respostas
                st.session_state["observacoes_temp"] = observacoes
                st.session_state["pendencias_manuais"] = pendencias_manuais
                st.session_state["etapa"] = "4. Revisão"
                st.rerun()
            else:
                st.error(f"⚠️ Responda todas as perguntas antes de prosseguir ({total - preenchidas} pendentes)")

# ============================================
# ETAPA 4 - REVISÃO
# ============================================
elif st.session_state["etapa"] == "4. Revisão":
    st.header("📋 Revisão da análise")
    
    respostas = st.session_state.get("respostas_temp", {})
    observacoes = st.session_state.get("observacoes_temp", {})
    pendencias_manuais = st.session_state.get("pendencias_manuais", {})
    
    preenchidas, total, pct = progresso_percentual(respostas)
    render_progresso(preenchidas, total, pct, st)
    
    conclusao = definir_conclusao(respostas, pendencias_manuais)
    grupos_inconformes = montar_inconformidades_por_grupo(respostas, observacoes, pendencias_manuais)
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📌 Resumo")
        st.write(f"**Protocolo:** {st.session_state['protocolo']}")
        st.write(f"**Requerente:** {st.session_state['interessado']}")
        st.write(f"**Analista:** {st.session_state['analista']}")
        
        if conclusao == "FAVORÁVEL":
            st.success(f"✅ Conclusão: {conclusao}")
        else:
            st.error(f"❌ Conclusão: {conclusao}")
    
    with col2:
        st.subheader("📊 Estatísticas")
        total_inconformes = sum(len(v) for v in grupos_inconformes.values())
        st.metric("Perguntas", total)
        st.metric("Respondidas", preenchidas)
        st.metric("Inconformidades", total_inconformes)
    
    # Gráfico de inconformidades
    fig = gerar_grafico_inconformidades(respostas, grupos_inconformes)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Voltar", use_container_width=True):
            st.session_state["etapa"] = "3. Análise"
            st.rerun()
    with col2:
        if st.button("Prosseguir →", use_container_width=True, type="primary"):
            salvar_analise_analista(
                st.session_state["protocolo"],
                st.session_state["analista"],
                st.session_state.get("papel", "Analista"),
                respostas,
                observacoes,
                pendencias_manuais
            )
            st.session_state["etapa"] = "5. Gerar parecer"
            st.rerun()

# ============================================
# ETAPA 5 - GERAR PARECER
# ============================================
elif st.session_state["etapa"] == "5. Gerar parecer":
    st.header("📄 Geração do parecer")
    
    respostas = st.session_state.get("respostas_temp", {})
    observacoes = st.session_state.get("observacoes_temp", {})
    pendencias_manuais = st.session_state.get("pendencias_manuais", {})
    
    dados = {
        "protocolo": st.session_state.get("protocolo", ""),
        "tipo": st.session_state.get("tipo", ""),
        "interessado": st.session_state.get("interessado", ""),
        "n_lotes": st.session_state.get("n_lotes", 1),
        "matriculas": st.session_state.get("matriculas", "")
    }
    
    conclusao = definir_conclusao(respostas, pendencias_manuais)
    
    st.subheader("📋 Dados do Parecer")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Protocolo:** {dados['protocolo']}")
        st.write(f"**Requerente:** {dados['interessado']}")
    with col2:
        st.write(f"**Analista:** {st.session_state['analista']}")
        st.write(f"**Conclusão:** {conclusao}")
    
    if conclusao == "FAVORÁVEL":
        st.success(f"✅ Conclusão final: {conclusao}")
    else:
        st.error(f"❌ Conclusão final: {conclusao}")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Voltar", use_container_width=True):
            st.session_state["etapa"] = "4. Revisão"
            st.rerun()
    with col2:
        if st.button("📄 Gerar Parecer", use_container_width=True, type="primary"):
            if not dados["protocolo"]:
                st.error("Protocolo não informado")
            elif not os.path.exists("modelo_parecer.docx"):
                st.error("modelo_parecer.docx não encontrado")
            else:
                try:
                    with st.spinner("Gerando parecer..."):
                        arquivo = gerar_docx(dados, respostas, observacoes, conclusao,
                                            st.session_state["analista"], st.session_state["matricula_analista"],
                                            st.session_state["setor"], st.session_state["n_analise"],
                                            pendencias_manuais)
                        nome = f"PU_{dados['protocolo'].replace('/', '-')}_AN{st.session_state['n_analise']}.docx"
                        st.success("✅ Parecer gerado!")
                        st.download_button("⬇️ Baixar", data=arquivo, file_name=nome, use_container_width=True)
                except Exception as e:
                    st.error(f"Erro: {e}")

# ============================================
# ETAPA 6 - DASHBOARD
# ============================================
elif st.session_state["etapa"] == "6. Dashboard":
    st.header("📊 Dashboard de Métricas")
    
    if not tem_permissao(2):
        st.error("❌ Acesso negado! Apenas Estagiários Sênior e Analistas Responsáveis podem acessar o Dashboard.")
    else:
        tempo_medio = calcular_tempo_medio_analise()
        if tempo_medio:
            st.metric("⏱️ Tempo Médio de Análise", f"{tempo_medio:.1f} dias")
        
        fig_tempo = gerar_grafico_tempo_analises()
        if fig_tempo:
            st.plotly_chart(fig_tempo, use_container_width=True)
        
        st.subheader("🔍 Busca Avançada")
        
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            termo_busca_dash = st.text_input("Protocolo", placeholder="Digite o protocolo...")
        with col_f2:
            filtro_status = st.selectbox("Status", ["Todos", "FAVORÁVEL", "DESFAVORÁVEL", "Em análise"])
        with col_f3:
            filtro_analista = st.text_input("Analista", placeholder="Digite o nome...")
        
        if st.button("🔍 Buscar", use_container_width=True):
            resultados = buscar_protocolos(termo_busca_dash, filtro_status if filtro_status != "Todos" else None,
                                           filtro_analista if filtro_analista else None)
            
            if resultados:
                st.subheader(f"📋 Resultados encontrados: {len(resultados)}")
                df_resultados = pd.DataFrame(resultados)
                st.dataframe(df_resultados, use_container_width=True)
            else:
                st.info("Nenhum protocolo encontrado")

# ============================================
# ETAPA 7 - COMPARADOR
# ============================================
elif st.session_state["etapa"] == "7. Comparador":
    if not tem_permissao(3):
        st.error("❌ Acesso negado! Apenas Analistas Responsáveis podem acessar o Comparador.")
        if st.button("← Voltar ao menu principal"):
            st.session_state["etapa"] = "1. Protocolo"
            st.rerun()
    else:
        st.header("🔍 Comparador de Análises")
        
        protocolo_comp = st.text_input("N° Protocolo para comparar", value=st.session_state.get("protocolo", ""))
        
        if protocolo_comp:
            render_comparador_analises(protocolo_comp)
