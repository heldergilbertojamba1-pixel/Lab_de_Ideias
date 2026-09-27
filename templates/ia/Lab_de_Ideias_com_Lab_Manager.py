from flask import Flask, request, redirect, url_for, session, render_template_string, abort, send_file
import sqlite3
import importlib.util
from datetime import datetime
import os
import secrets
import hmac
import time
from urllib.parse import quote
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "lab_de_ideias.db")

app.secret_key = os.environ.get("LAB_SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False

WHATSAPP = "244942552508"
PHONE = "+244932115820"
EMAIL = "heldergilbertojamba1@email.com"
LOCATION = "Moçâmedes, Namibe, Angola"
IBAN = "0040 0000 36907614101 27"
EXPRESS = "932115820"
FOUNDER = "Hélder Gilberto Jamba"

# ============================================================
# LAB MANAGER INTEGRADO
# ============================================================
LAB_MANAGER_CANDIDATES = [
    os.path.join(BASE, "Lab Manager", "Lab_Manager_Inteligente_v3.py"),
    os.path.join(BASE, "Lab_Manager_Inteligente_v3.py"),
]
LAB_MANAGER_MODULE = None

def carregar_lab_manager():
    global LAB_MANAGER_MODULE
    if LAB_MANAGER_MODULE is not None:
        return LAB_MANAGER_MODULE
    for caminho in LAB_MANAGER_CANDIDATES:
        if os.path.isfile(caminho):
            try:
                spec = importlib.util.spec_from_file_location("lab_manager_integrado", caminho)
                modulo = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(modulo)
                if hasattr(modulo, "inicializar_banco"):
                    modulo.inicializar_banco()
                LAB_MANAGER_MODULE = modulo
                print("Lab Manager integrado:", caminho)
                return modulo
            except Exception as erro:
                print("Erro ao carregar Lab Manager:", erro)
                return None
    print("Aviso: Lab_Manager_Inteligente_v3.py não encontrado.")
    return None

def lab_manager_responder(pergunta, idioma="pt"):
    modulo = carregar_lab_manager()
    if modulo is None or not hasattr(modulo, "responder_assistente"):
        return "O Lab Manager ainda não encontrou o ficheiro do assistente. Coloque Lab_Manager_Inteligente_v3.py dentro da pasta 'Lab Manager'."
    try:
        return modulo.responder_assistente(pergunta, idioma)
    except Exception as erro:
        print("ERRO LAB MANAGER:", erro)
        return "O Lab Manager recebeu a mensagem, mas encontrou um erro ao processá-la."

def sincronizar_pedido_com_lab_manager(nome, telefone, email, servico, mensagem):
    modulo = carregar_lab_manager()
    if modulo is None or not hasattr(modulo, "conectar"):
        return
    db = None
    try:
        db = modulo.conectar()
        cur = db.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("SELECT id FROM clientes WHERE telefone = ?", (telefone,))
        cliente = cur.fetchone()
        if cliente:
            cliente_id = cliente["id"]
            cur.execute("UPDATE clientes SET nome=?, email=? WHERE id=?", (nome, email, cliente_id))
        else:
            cur.execute(
                "INSERT INTO clientes (nome, telefone, email, criado_em) VALUES (?, ?, ?, ?)",
                (nome, telefone, email, agora)
            )
            cliente_id = cur.lastrowid
        cur.execute(
            """INSERT INTO pedidos
               (cliente_id, descricao, valor, status, localizacao, criado_em)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cliente_id, f"{servico}: {mensagem or 'Sem mensagem'}", 0, "Pendente", LOCATION, agora)
        )
        db.commit()
    except Exception as erro:
        print("Aviso: sincronização com Lab Manager falhou:", erro)
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


# ============================================================
# LOGOTIPO
# Estrutura do projeto: static/images/Logotipo.png
# ============================================================
LOGO_PATH = os.path.join(BASE, "static", "images", "Logotipo.png")

# ============================================================
# FOTOS DOS PRODUTOS
# As fotos adicionadas pelo administrador ficam aqui.
# ============================================================
PRODUCT_UPLOAD_DIR = os.path.join(BASE, "static", "uploads", "produtos")
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
MAX_PRODUCT_PHOTOS = 20
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
os.makedirs(PRODUCT_UPLOAD_DIR, exist_ok=True)

# ============================================================
# SERVIÇOS OFICIAIS
# ============================================================

SERVICES = [
    {
        "name": "Gestão de Redes Sociais",
        "slug": "gestao-de-redes-sociais",
        "price": "A partir de 30.000 Kz/mês",
        "hook": "A sua marca merece mais do que publicar. Merece presença, estratégia e consistência.",
        "items": ["Planeamento de conteúdos", "Gestão de páginas", "Calendário editorial", "Acompanhamento da presença digital"]
    },
    {
        "name": "Agendamento de Conteúdos",
        "slug": "agendamento-de-conteudos",
        "price": "A partir de 15.000 Kz",
        "hook": "Não deixe a sua marca desaparecer no silêncio das redes. Organize hoje o conteúdo de amanhã.",
        "items": ["Organização de publicações", "Calendário de posts", "Programação de conteúdos", "Planeamento de horários"]
    },
    {
        "name": "Criação de Conteúdo",
        "slug": "criacao-de-conteudo",
        "price": "A partir de 20.000 Kz",
        "hook": "Conteúdo sem estratégia é apenas publicação. Transforme ideias em conteúdo que chama atenção.",
        "items": ["Instagram", "Facebook", "TikTok", "Stories", "Reels", "Conteúdo promocional"]
    },
    {
        "name": "Edição de Vídeos",
        "slug": "edicao-de-videos",
        "price": "A partir de 10.000 Kz",
        "hook": "O seu vídeo pode ser visto ou pode ser lembrado. A edição faz a diferença.",
        "items": ["Reels", "TikTok", "Stories", "Vídeos promocionais", "Anúncios", "Cortes e montagem"]
    },
    {
        "name": "Identidade Visual",
        "slug": "identidade-visual",
        "price": "A partir de 30.000 Kz",
        "hook": "Antes de alguém conhecer a sua marca, os seus olhos já formaram uma opinião.",
        "items": ["Logotipo", "Paleta de cores", "Tipografia", "Elementos visuais", "Aplicações da marca"]
    },
    {
        "name": "Copywriting",
        "slug": "copywriting",
        "price": "A partir de 10.000 Kz",
        "hook": "As palavras certas não apenas informam. Elas despertam interesse e levam à ação.",
        "items": ["Legendas", "Textos para anúncios", "Chamadas para ação", "Textos promocionais", "Copy para redes sociais"]
    },
    {
        "name": "Marketing Digital",
        "slug": "marketing-digital",
        "price": "A partir de 25.000 Kz",
        "hook": "Estar na internet não basta. A sua presença precisa trabalhar a favor do seu negócio.",
        "items": ["Estratégia digital", "Posicionamento", "Campanhas", "Planeamento", "Orientação para presença online"]
    },
    {
        "name": "Divulgação de Negócios",
        "slug": "divulgacao-de-negocios",
        "price": "A partir de 10.000 Kz",
        "hook": "Se as pessoas certas não conhecem o seu negócio, estão a comprar de outra pessoa.",
        "items": ["Divulgação nas redes", "Campanhas promocionais", "Conteúdo de divulgação", "Ações para aumentar alcance"]
    },
    {
        "name": "Criação de Sites",
        "slug": "criacao-de-sites",
        "price": "A partir de 100.000 Kz",
        "hook": "O seu negócio merece um espaço digital profissional, moderno e preparado para o telemóvel.",
        "items": ["Site profissional", "Design responsivo", "Páginas para negócios", "Formulários de contacto", "Integração com WhatsApp", "Estrutura personalizada"]
    },
]

# ============================================================
# PRODUTOS
# ============================================================

PRODUCTS = [
    # Perfumaria e cuidados
    {"name": "Perfumes", "slug": "perfumes", "icon": "🌹", "group": "Perfumaria e cuidados", "items": ["Perfumes", "Fragrâncias selecionadas"]},
    {"name": "Creme para o cabelo", "slug": "creme-para-o-cabelo", "icon": "✨", "group": "Perfumaria e cuidados", "items": ["Creme para o cabelo"]},
    {"name": "Creme para a pele", "slug": "creme-para-a-pele", "icon": "🧴", "group": "Perfumaria e cuidados", "items": ["Creme para a pele"]},
    {"name": "Óleo perfumado", "slug": "oleo-perfumado", "icon": "💎", "group": "Perfumaria e cuidados", "items": ["Óleo perfumado"]},

    # Cartões
    {"name": "Cartões personalizados", "slug": "cartoes-personalizados", "icon": "💌", "group": "Personalizados", "items": ["Cartões personalizados"]},

    # Roupas e calçados, cada categoria com as suas próprias fotos
    {"name": "Calças", "slug": "calcas", "icon": "👖", "group": "Roupas e calçados", "items": ["Calças"]},
    {"name": "Calções", "slug": "calcoes", "icon": "🩳", "group": "Roupas e calçados", "items": ["Calções"]},
    {"name": "Vestidos", "slug": "vestidos", "icon": "👗", "group": "Roupas e calçados", "items": ["Vestidos"]},
    {"name": "Saias", "slug": "saias", "icon": "👗", "group": "Roupas e calçados", "items": ["Saias"]},
    {"name": "Calçados", "slug": "calcados", "icon": "👟", "group": "Roupas e calçados", "items": ["Calçados", "Sapatos"]},
    {"name": "Camisolas", "slug": "camisolas", "icon": "👕", "group": "Roupas e calçados", "items": ["Camisolas"]},
    {"name": "Casacos", "slug": "casacos", "icon": "🧥", "group": "Roupas e calçados", "items": ["Casacos"]},
    {"name": "Sandálias", "slug": "sandalias", "icon": "👡", "group": "Roupas e calçados", "items": ["Sandálias"]},

    # Utensílios e acessórios
    {"name": "Relógios", "slug": "relogios", "icon": "⌚", "group": "Utensílios e acessórios", "items": ["Relógios"]},
    {"name": "Bandoletes", "slug": "bandoletes", "icon": "🎀", "group": "Utensílios e acessórios", "items": ["Bandoletes"]},
    {"name": "Kit de casamento", "slug": "kit-de-casamento", "icon": "💍", "group": "Utensílios e acessórios", "items": ["Kit de casamento"]},
    {"name": "Utensílios domésticos", "slug": "utensilios-domesticos", "icon": "🏠", "group": "Utensílios e acessórios", "items": ["Utensílios domésticos"]},
    {"name": "Outros artigos selecionados", "slug": "outros-artigos-selecionados", "icon": "🛍️", "group": "Utensílios e acessórios", "items": ["Outros artigos selecionados"]},
]

STATES = ["Novo", "Em análise", "Em andamento", "Concluído", "Cancelado"]

# ============================================================
# BANCO DE DADOS
# ============================================================

def conectar():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def ensure_column(cur, table, column, definition):
    cur.execute("PRAGMA table_info(" + table + ")")
    columns = [row["name"] for row in cur.fetchall()]
    if column not in columns:
        cur.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " " + definition)

def init_db():
    db = conectar()
    cur = db.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT NOT NULL,
            email TEXT,
            servico TEXT NOT NULL,
            mensagem TEXT,
            estado TEXT NOT NULL DEFAULT 'Novo',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT UNIQUE NOT NULL,
            email TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    ensure_column(cur, "pedidos", "email", "TEXT")
    ensure_column(cur, "pedidos", "mensagem", "TEXT")
    ensure_column(cur, "pedidos", "estado", "TEXT NOT NULL DEFAULT 'Novo'")
    ensure_column(cur, "pedidos", "criado_em", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    ensure_column(cur, "clientes", "email", "TEXT")
    ensure_column(cur, "clientes", "criado_em", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS produto_fotos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_slug TEXT NOT NULL,
            nome_arquivo TEXT NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.commit()
    db.close()

init_db()

# ============================================================
# AUXILIARES
# ============================================================

def encontrar_logo():
    if os.path.isfile(LOGO_PATH):
        return LOGO_PATH
    return None

def wa(texto):
    return "https://wa.me/" + WHATSAPP + "?text=" + quote(texto)

def csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]

def validar_csrf():
    token = request.form.get("csrf_token", "")
    esperado = session.get("csrf_token", "")
    if not esperado or not hmac.compare_digest(token, esperado):
        abort(400)

def service_by_slug(slug):
    return next((s for s in SERVICES if s["slug"] == slug), None)

def product_by_slug(slug):
    return next((p for p in PRODUCTS if p["slug"] == slug), None)

def fotos_produto(slug):
    db = conectar()
    dados = db.execute(
        "SELECT id, nome_arquivo, criado_em FROM produto_fotos WHERE produto_slug = ? ORDER BY id DESC",
        (slug,)
    ).fetchall()
    db.close()
    return dados

def extensao_permitida(nome):
    return "." in nome and nome.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

# ============================================================
# DESIGN PREMIUM
# ============================================================

CSS = """
:root{
 --black:#070707;
 --black2:#101010;
 --gold:#d4af37;
 --gold2:#f2d878;
 --white:#fff;
 --muted:#b9b9b9;
 --line:rgba(212,175,55,.24);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
 margin:0;
 font-family:Arial,Helvetica,sans-serif;
 background:var(--black);
 color:var(--white);
 line-height:1.6;
}
a{text-decoration:none;color:inherit}
.container{width:min(1120px,92%);margin:auto}
.nav{
 position:sticky;top:0;z-index:100;
 background:rgba(7,7,7,.96);
 border-bottom:1px solid var(--line);
 backdrop-filter:blur(12px);
}
.nav-inner{
 min-height:74px;
 display:flex;
 align-items:center;
 justify-content:space-between;
 gap:18px;
}
.brand{display:flex;align-items:center;gap:12px;font-weight:800}
.brand img{width:48px;height:48px;object-fit:contain}
.brand-text span{display:block;color:var(--gold);font-size:11px;margin-top:2px}
.menu{display:flex;gap:17px;flex-wrap:wrap;font-size:14px}
.menu a:hover{color:var(--gold2)}
.hero{
 padding:82px 0 72px;
 background:
 radial-gradient(circle at 85% 12%,rgba(212,175,55,.16),transparent 30%),
 radial-gradient(circle at 10% 80%,rgba(212,175,55,.07),transparent 28%);
}
.hero-grid{display:grid;grid-template-columns:1.2fr .8fr;gap:42px;align-items:center}
.badge{
 display:inline-block;
 padding:7px 13px;
 border:1px solid var(--line);
 border-radius:999px;
 color:var(--gold2);
 text-transform:uppercase;
 letter-spacing:1.4px;
 font-size:11px;
}
h1{font-size:clamp(38px,7vw,72px);line-height:1.02;margin:18px 0}
h2{font-size:clamp(28px,4vw,42px);line-height:1.15;margin:0 0 14px}
h3{margin:6px 0}
.gold{color:var(--gold2)}
.lead{font-size:19px;color:#dedede;max-width:700px}
.hero-card,.card{
 background:linear-gradient(145deg,#151515,#0b0b0b);
 border:1px solid var(--line);
 border-radius:22px;
 padding:25px;
 box-shadow:0 16px 50px rgba(0,0,0,.28);
}
.hero-logo{min-height:340px;display:flex;align-items:center;justify-content:center}
.hero-logo img{width:min(300px,78%);max-height:300px;object-fit:contain}
.btn{
 display:inline-flex;align-items:center;justify-content:center;gap:8px;
 padding:13px 19px;border-radius:12px;
 border:1px solid var(--gold);font-weight:700;cursor:pointer;
 transition:.2s;
}
.btn-gold{background:var(--gold);color:#080808}
.btn-gold:hover{background:var(--gold2);transform:translateY(-1px)}
.btn-dark{background:#111;color:#fff}
.btn-dark:hover{color:var(--gold2)}
.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:24px}
section{padding:70px 0}
.section-head{margin-bottom:30px}
.section-head p{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.service-card,.product-card{display:flex;flex-direction:column;gap:10px}
.product-photo,.product-placeholder{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:16px;border:1px solid var(--line);background:#0b0b0b}
.product-placeholder{display:flex;align-items:center;justify-content:center;font-size:64px}
.product-group-title{margin:42px 0 16px;color:var(--gold2);font-size:24px}
.product-group:first-of-type{margin-top:0}
.product-photo{width:100%;height:230px;object-fit:cover;border-radius:16px;border:1px solid var(--line);background:#080808}
.photo-gallery{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:20px}
.photo-gallery img{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:16px;border:1px solid var(--line);background:#080808}
.photo-admin-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:18px}
.photo-admin-card{background:#0d0d0d;border:1px solid #292929;border-radius:14px;padding:10px}
.photo-admin-card img{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:10px}
.photo-admin-card form{margin-top:8px}
.upload-box{border:1px dashed var(--gold);border-radius:16px;padding:18px;background:#0d0d0d}
.service-card .price,.product-card .price{color:var(--gold2);font-weight:800}
.hook{color:#eee;font-weight:600}
.muted{color:var(--muted)}
ul.clean{padding-left:20px;color:#ddd}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:30px}
.stat{padding:20px;border:1px solid var(--line);border-radius:16px;background:#0d0d0d}
.stat strong{display:block;font-size:30px;color:var(--gold2)}
.page-head{padding:65px 0 30px}
.detail-grid{display:grid;grid-template-columns:1.1fr .9fr;gap:25px}
.price-box{font-size:26px;color:var(--gold2);font-weight:800;margin:15px 0}
.notice{
 border-left:3px solid var(--gold);
 padding:14px 16px;background:#121212;color:#ddd;border-radius:8px;
}
form{display:grid;gap:13px}
input,textarea,select{
 width:100%;padding:14px 15px;border-radius:11px;
 border:1px solid #333;background:#090909;color:#fff;outline:none;
}
input:focus,textarea:focus,select:focus{border-color:var(--gold)}
textarea{min-height:120px;resize:vertical}
label{font-weight:700;font-size:14px}
.footer{border-top:1px solid var(--line);padding:38px 0;color:#aaa}
.footer-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
.admin-wrap{overflow-x:auto}
.admin-table{width:100%;border-collapse:collapse}
.admin-table th,.admin-table td{
 padding:12px;border-bottom:1px solid #292929;
 text-align:left;vertical-align:top;
}
.notice-error{border-color:#6b2d2d;background:#210f0f}
@media(max-width:800px){
 .hero-grid,.detail-grid,.grid,.footer-grid,.stats,.photo-gallery,.photo-admin-grid{grid-template-columns:1fr}
 .nav-inner{align-items:flex-start;padding:12px 0;flex-direction:column}
 .menu{gap:11px}
 section{padding:50px 0}
 .hero{padding:55px 0}
 .hero-logo{min-height:240px}
 .admin-table{font-size:13px}
}
"""

def render_page(title, content):
    logo = url_for("static", filename="images/Logotipo.png")
    return render_template_string("""
<!doctype html>
<html lang="pt">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{title}} | Lab de Ideias</title>
<style>{{css|safe}}</style>
</head>
<body>
<nav class="nav">
 <div class="container nav-inner">
  <a class="brand" href="{{url_for('home')}}">
   {% if logo %}<img src="{{logo}}" alt="Logotipo Lab de Ideias">{% endif %}
   <div class="brand-text">
    Lab de Ideias
    <span>Produtos • Serviços • Soluções Digitais</span>
   </div>
  </a>
  <div class="menu">
   <a href="{{url_for('home')}}">Início</a>
   <a href="{{url_for('home')}}#projeto">Projeto</a>
   <a href="{{url_for('home')}}#servicos">Serviços</a>
   <a href="{{url_for('home')}}#produtos">Produtos</a>
   <a href="{{url_for('home')}}#contacto">Contacto</a>
  </div>
 </div>
</nav>
{{content|safe}}
<a class="lab-ai-float" href="{{url_for('lab_manager')}}" aria-label="Abrir Lab Manager">🤖 <strong>Lab Manager</strong></a>
<footer class="footer">
 <div class="container footer-grid">
  <div><strong class="gold">Lab de Ideias</strong><br>Produtos • Serviços • Soluções Digitais</div>
  <div>{{location}}<br>Fundador: {{founder}}</div>
  <div>WhatsApp: +{{whatsapp}}<br>Email: {{email}}</div>
 </div>
</footer>
</body>
</html>
""", title=title, content=content, css=CSS, logo=logo,
       location=LOCATION, founder=FOUNDER, whatsapp=WHATSAPP, email=EMAIL)

# ============================================================
# LOGO
# ============================================================

@app.route("/logotipo.png")
def logotipo():
    if not os.path.isfile(LOGO_PATH):
        abort(404)
    return send_file(LOGO_PATH, mimetype="image/png")

@app.route("/produto-foto/<path:filename>")
def foto_produto(filename):
    caminho = os.path.join(PRODUCT_UPLOAD_DIR, os.path.basename(filename))
    if not os.path.isfile(caminho):
        abort(404)
    return send_file(caminho)

# ============================================================
# INÍCIO
# ============================================================

@app.route("/")
def home():
    logo = url_for("static", filename="images/Logotipo.png")

    service_cards = ""
    for s in SERVICES:
        service_cards += f"""
        <article class="card service-card">
          <div class="gold">SERVIÇO</div>
          <h3>{s["name"]}</h3>
          <p class="hook">{s["hook"]}</p>
          <div class="price">{s["price"]}</div>
          <a class="btn btn-dark" href="{url_for("servico", slug=s["slug"])}">Ver serviço</a>
        </article>
        """

    product_cards = ""
    grupos = []
    for p in PRODUCTS:
        if p.get("group") not in grupos:
            grupos.append(p.get("group"))

    for grupo in grupos:
        cards_grupo = ""
        for p in [x for x in PRODUCTS if x.get("group") == grupo]:
            items = "".join(f"<li>{item}</li>" for item in p["items"])
            fotos = fotos_produto(p["slug"])
            foto_html = (
                f'<img class="product-photo" src="{url_for("foto_produto", filename=fotos[0]["nome_arquivo"])}" alt="Foto de {p["name"]}">'
                if fotos else f'<div class="product-placeholder">{p["icon"]}</div>'
            )
            cards_grupo += f"""
            <article class="card product-card">
              {foto_html}
              <h3>{p["name"]}</h3>
              <ul class="clean">{items}</ul>
              <div class="price">Preço: A definir</div>
              <a class="btn btn-dark" href="{url_for("produto", slug=p["slug"])}">Ver detalhes</a>
            </article>
            """
        product_cards += f'<h3 class="product-group-title">{grupo}</h3><div class="grid product-group">{cards_grupo}</div>'

    options = "".join(
        f'<option value="{s["name"]}">{s["name"]}</option>' for s in SERVICES
    )

    content = f"""
<section class="hero">
 <div class="container hero-grid">
  <div>
   <span class="badge">Moçâmedes • Namibe • Angola</span>
   <h1>Ideias que transformam <span class="gold">presença</span> em valor.</h1>
   <p class="lead">O Lab de Ideias ajuda negócios, marcas e empreendedores a comunicar melhor, destacar-se no digital e transformar boas ideias em soluções.</p>
   <div class="actions">
    <a class="btn btn-gold" href="#servicos">Conhecer serviços</a>
    <a class="btn btn-dark" href="{wa("Olá, Lab de Ideias! Gostaria de conhecer os serviços.")}" target="_blank">Falar no WhatsApp</a>
   </div>
   <div class="stats">
    <div class="stat"><strong>9</strong>Serviços digitais</div>
    <div class="stat"><strong>{len(PRODUCTS)}</strong>Categorias de produtos</div>
    <div class="stat"><strong>∞</strong>Ideias por transformar</div>
   </div>
  </div>
  <div class="hero-card hero-logo">
   {f'<img src="{logo}" alt="Logotipo Lab de Ideias">' if logo else '<div style="text-align:center"><div style="font-size:75px">💡</div><h2 class="gold">Lab de Ideias</h2></div>'}
  </div>
 </div>
</section>

<section id="projeto">
 <div class="container">
  <div class="section-head">
   <h2>O que é o <span class="gold">Lab de Ideias?</span></h2>
   <p>Criatividade • Qualidade • Inovação</p>
  </div>
  <div class="detail-grid">
   <div class="card">
    <h3>Mais do que presença digital</h3>
    <p>O Lab de Ideias é um projeto dedicado a ajudar negócios, marcas e empreendedores a apresentar melhor as suas ideias e construir uma presença profissional.</p>
    <p class="hook">A sua ideia pode ser boa. A forma como ela é apresentada pode torná-la impossível de ignorar.</p>
   </div>
   <div class="card">
    <h3>Produtos • Serviços • Soluções Digitais</h3>
    <p>Serviços digitais para quem quer comunicar, divulgar, organizar e crescer. Produtos selecionados para complementar essa visão.</p>
   </div>
  </div>
 </div>
</section>

<section id="servicos">
 <div class="container">
  <div class="section-head">
   <h2>Serviços que dão forma às suas <span class="gold">ideias.</span></h2>
   <p>Cada serviço tem a sua própria página para conhecer melhor a solução.</p>
  </div>
  <div class="grid">{service_cards}</div>
 </div>
</section>

<section id="produtos">
 <div class="container">
  <div class="section-head">
   <h2>Produtos selecionados, <span class="gold">sem complicação.</span></h2>
   <p>Cada categoria possui a sua própria galeria de fotos. Disponibilidade, modelos, tamanhos, cores e preços podem variar. Consulte o Lab antes de comprar.</p>
  </div>
  <div class="grid">{product_cards}</div>
 </div>
</section>

<section id="contacto">
 <div class="container">
  <div class="section-head">
   <h2>Vamos tirar a sua ideia do <span class="gold">papel?</span></h2>
   <p>Envie o pedido e será encaminhado para o WhatsApp do Lab de Ideias.</p>
  </div>
  <div class="detail-grid">
   <div class="card">
    <form method="post" action="{url_for("pedido")}">
     <input type="hidden" name="csrf_token" value="{csrf()}">
     <div><label>Nome</label><input name="nome" required maxlength="100" placeholder="Seu nome"></div>
     <div><label>Telefone</label><input name="telefone" required maxlength="30" placeholder="Seu número"></div>
     <div><label>Email</label><input type="email" name="email" maxlength="150" placeholder="seu@email.com"></div>
     <div><label>Serviço</label><select name="servico" required><option value="">Selecione</option>{options}</select></div>
     <div><label>Mensagem</label><textarea name="mensagem" maxlength="2000" placeholder="Conte brevemente o que precisa..."></textarea></div>
     <button class="btn btn-gold" type="submit">Solicitar serviço</button>
    </form>
   </div>
   <div class="card">
    <h3>Contacto</h3>
    <p><strong>Localização:</strong><br>{LOCATION}</p>
    <p><strong>WhatsApp:</strong><br>+{WHATSAPP}</p>
    <p><strong>Telefone:</strong><br>{PHONE}</p>
    <p><strong>Email:</strong><br>{EMAIL}</p>
    <p><strong>Express:</strong><br>{EXPRESS}</p>
    <p><strong>IBAN:</strong><br>{IBAN}</p>
    <a class="btn btn-gold" href="{wa("Olá, Lab de Ideias! Vim pelo site e gostaria de atendimento.")}" target="_blank">Abrir WhatsApp</a>
   </div>
  </div>
 </div>
</section>
"""
    return render_page("Início", content)

# ============================================================
# PÁGINA INDIVIDUAL DE SERVIÇO
# ============================================================

@app.route("/servico/<slug>")
def servico(slug):
    service = service_by_slug(slug)
    if not service:
        abort(404)

    items = "".join(f"<li>{item}</li>" for item in service["items"])
    msg = f"Olá, Lab de Ideias! Tenho interesse no serviço de {service['name']}."

    content = f"""
<section class="page-head">
 <div class="container">
  <span class="badge">Serviço Lab de Ideias</span>
  <h1>{service["name"]}</h1>
  <p class="lead">{service["hook"]}</p>
 </div>
</section>
<section>
 <div class="container detail-grid">
  <div class="card">
   <h2>O que inclui</h2>
   <ul class="clean">{items}</ul>
   <div class="notice">Cada projeto é avaliado conforme a complexidade, quantidade de trabalho e necessidades do cliente.</div>
  </div>
  <div class="card">
   <div class="gold">INVESTIMENTO INICIAL</div>
   <div class="price-box">{service["price"]}</div>
   <p class="muted">O preço final pode variar conforme a complexidade do projeto.</p>
   <div class="actions">
    <a class="btn btn-gold" href="{wa(msg)}" target="_blank">Solicitar este serviço</a>
    <a class="btn btn-dark" href="{url_for("home")}#servicos">Ver outros serviços</a>
   </div>
  </div>
 </div>
</section>
"""
    return render_page(service["name"], content)

# ============================================================
# PÁGINA INDIVIDUAL DE PRODUTO
# ============================================================

@app.route("/produto/<slug>")
def produto(slug):
    product = product_by_slug(slug)
    if not product:
        abort(404)

    items = "".join(f"<li>{item}</li>" for item in product["items"])
    fotos = fotos_produto(product["slug"])
    galeria = (
        '<div class="photo-gallery">' +
        ''.join(f'<img src="{url_for("foto_produto", filename=f["nome_arquivo"])}" alt="{product["name"]}">' for f in fotos) +
        '</div>'
        if fotos else
        '<div class="notice">Ainda não há fotos publicadas nesta categoria.</div>'
    )
    msg = f"Olá, Lab de Ideias! Gostaria de saber a disponibilidade e o preço de {product['name']}."

    content = f"""
<section class="page-head">
 <div class="container">
  <span class="badge">Produto</span>
  <h1>{product["icon"]} {product["name"]}</h1>
  <p class="lead">Consulte o Lab para conhecer os artigos disponíveis no momento.</p>
 </div>
</section>
<section>
 <div class="container">
  <div class="card">
   <h2>Fotos dos produtos</h2>
   {galeria}
  </div>
  <br>
  <div class="detail-grid">
   <div class="card">
    <h2>Itens da categoria</h2>
    <ul class="clean">{items}</ul>
   </div>
   <div class="card">
    <div class="price-box">Preço: A definir</div>
    <div class="notice">Disponibilidade, modelos, tamanhos, cores e preços podem variar. Consulte o Lab de Ideias antes de comprar.</div>
    <div class="actions">
     <a class="btn btn-gold" href="{wa(msg)}" target="_blank">Consultar no WhatsApp</a>
     <a class="btn btn-dark" href="{url_for("home")}#produtos">Voltar aos produtos</a>
    </div>
   </div>
  </div>
 </div>
</section>
"""
    return render_page(product["name"], content)

# ============================================================
# RECEBER PEDIDO
# ============================================================

@app.route("/pedido", methods=["POST"])
def pedido():
    validar_csrf()

    nome = request.form.get("nome", "").strip()
    telefone = request.form.get("telefone", "").strip()
    email = request.form.get("email", "").strip()
    servico_nome = request.form.get("servico", "").strip()
    mensagem = request.form.get("mensagem", "").strip()

    if not nome or not telefone or not servico_nome:
        abort(400)

    service = next((s for s in SERVICES if s["name"] == servico_nome), None)
    if not service:
        abort(400)

    db = conectar()
    cur = db.cursor()

    cur.execute("""
        INSERT INTO pedidos
        (nome, telefone, email, servico, mensagem, estado)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (nome, telefone, email, servico_nome, mensagem, "Novo"))

    cur.execute("SELECT id FROM clientes WHERE telefone = ?", (telefone,))
    cliente = cur.fetchone()

    if cliente:
        cur.execute("""
            UPDATE clientes
            SET nome = ?, email = ?
            WHERE telefone = ?
        """, (nome, email, telefone))
    else:
        try:
            cur.execute("""
                INSERT INTO clientes (nome, telefone, email)
                VALUES (?, ?, ?)
            """, (nome, telefone, email))
        except sqlite3.IntegrityError:
            cur.execute("""
                UPDATE clientes
                SET nome = ?, email = ?
                WHERE telefone = ?
            """, (nome, email, telefone))

    db.commit()
    db.close()

    sincronizar_pedido_com_lab_manager(nome, telefone, email, servico_nome, mensagem)

    texto = (
        f"Olá, Lab de Ideias!%0A%0A"
        f"Gostaria de solicitar o serviço: {service['name']}%0A"
        f"Nome: {nome}%0A"
        f"Telefone: {telefone}%0A"
        f"Email: {email or 'Não informado'}%0A"
        f"Mensagem: {mensagem or 'Sem mensagem adicional'}"
    )

    return redirect("https://wa.me/" + WHATSAPP + "?text=" + texto)

# ============================================================
# DASHBOARD ADMIN
# ============================================================

ADMIN_USER = "Hélder Jamba"
ADMIN_PASSWORD = os.environ.get("LAB_ADMIN_PASSWORD", "admin123")
LOGIN_ATTEMPTS = {}
LOCK_SECONDS = 300

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin"))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/admin", methods=["GET", "POST"])
def admin():
    erro = ""

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        key = request.remote_addr or "unknown"
        now = time.time()

        data = LOGIN_ATTEMPTS.get(key, {"count": 0, "until": 0})

        if now < data["until"]:
            erro = "Muitas tentativas. Aguarde alguns minutos."
        elif hmac.compare_digest(username, ADMIN_USER) and hmac.compare_digest(password, ADMIN_PASSWORD):
            LOGIN_ATTEMPTS.pop(key, None)
            session["admin"] = True
            return redirect(url_for("painel"))
        else:
            data["count"] += 1
            if data["count"] >= 5:
                data["until"] = now + LOCK_SECONDS
                data["count"] = 0
            LOGIN_ATTEMPTS[key] = data
            erro = "Utilizador ou senha incorretos."

    erro_html = f'<div class="notice notice-error">{erro}</div><br>' if erro else ""

    content = f"""
<section class="page-head">
 <div class="container">
  <span class="badge">Área reservada</span>
  <h1>Dashboard</h1>
  <p class="lead">Gestão dos pedidos e clientes do Lab de Ideias.</p>
 </div>
</section>
<section>
 <div class="container">
  <div class="card" style="max-width:520px;margin:auto">
   {erro_html}
   <form method="post">
    <div><label>Utilizador</label><input name="username" required autocomplete="username"></div>
    <div><label>Senha</label><input type="password" name="password" required autocomplete="current-password"></div>
    <button class="btn btn-gold" type="submit">Entrar</button>
   </form>
  </div>
 </div>
</section>
"""
    return render_page("Admin", content)

@app.route("/admin/painel")
@admin_required
def painel():
    db = conectar()
    cur = db.cursor()

    cur.execute("SELECT COUNT(*) AS total FROM pedidos")
    total_pedidos = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) AS total FROM clientes")
    total_clientes = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) AS total FROM pedidos WHERE estado = 'Novo'")
    novos = cur.fetchone()["total"]

    cur.execute("""
        SELECT id, nome, telefone, email, servico, mensagem, estado, criado_em
        FROM pedidos
        ORDER BY id DESC
    """)
    pedidos = cur.fetchall()

    db.close()

    rows = ""
    for p in pedidos:
        options = "".join(
            f'<option value="{state}" {"selected" if state == p["estado"] else ""}>{state}</option>'
            for state in STATES
        )

        rows += f"""
        <tr>
         <td>#{p["id"]}</td>
         <td><strong>{p["nome"]}</strong><br>{p["telefone"]}<br>{p["email"] or ""}</td>
         <td>{p["servico"]}</td>
         <td>{p["mensagem"] or "Sem mensagem"}</td>
         <td>{p["criado_em"] or ""}</td>
         <td>
          <form method="post" action="{url_for("atualizar_estado", order_id=p["id"])}">
           <input type="hidden" name="csrf_token" value="{csrf()}">
           <select name="estado">{options}</select>
           <button class="btn btn-dark" style="margin-top:7px;padding:8px 11px" type="submit">Atualizar</button>
          </form>
         </td>
        </tr>
        """

    tabela = (
        "<table class='admin-table'>"
        "<thead><tr><th>ID</th><th>Cliente</th><th>Serviço</th><th>Mensagem</th><th>Data</th><th>Estado</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        if rows else "<p class='muted'>Ainda não existem pedidos.</p>"
    )

    content = f"""
<section class="page-head">
 <div class="container">
  <span class="badge">Lab de Ideias</span>
  <h1>Dashboard</h1>
  <div class="actions">
   <a class="btn btn-dark" href="{url_for("home")}">Ver site</a>
   <a class="btn btn-gold" href="{url_for("admin_produtos")}">📸 Adicionar fotos aos produtos</a>
   <a class="btn btn-dark" href="{url_for("admin_sair")}">Sair</a>
  </div>
 </div>
</section>
<section>
 <div class="container">
  <div class="stats">
   <div class="stat"><strong>{total_pedidos}</strong>Pedidos</div>
   <div class="stat"><strong>{novos}</strong>Pedidos novos</div>
   <div class="stat"><strong>{total_clientes}</strong>Clientes</div>
  </div>
  <br>
  <div class="card">
   <h2>📸 Fotos dos produtos</h2>
   <p class="muted">Escolha diretamente a categoria e carregue as fotos. Cada categoria tem a sua própria galeria.</p>
   <div class="grid">
    {''.join(f'<article class="card"><h3>{p["icon"]} {p["name"]}</h3><p class="muted">Fotos: {len(fotos_produto(p["slug"]))}</p><a class="btn btn-gold" href="{url_for("admin_fotos_produto", slug=p["slug"])}">📷 Colocar fotos</a></article>' for p in PRODUCTS)}
   </div>
  </div>
  <br>
  <div class="card admin-wrap">
   <h2>Pedidos</h2>
   {tabela}
  </div>
 </div>
</section>
"""
    return render_page("Dashboard", content)

@app.route("/admin/produtos")
@admin_required
def admin_produtos():
    cards = ""
    for product in PRODUCTS:
        fotos = fotos_produto(product["slug"])
        thumb = (
            f'<img class="product-photo" src="{url_for("foto_produto", filename=fotos[0]["nome_arquivo"])}" alt="{product["name"]}">'
            if fotos else
            f'<div style="font-size:54px;text-align:center;padding:45px 0">{product["icon"]}</div>'
        )
        cards += f"""
        <article class="card">
          {thumb}
          <h3>{product["name"]}</h3>
          <p class="muted">{len(fotos)} foto(s) publicada(s)</p>
          <a class="btn btn-gold" href="{url_for("admin_fotos_produto", slug=product["slug"])}">📸 Adicionar / gerir fotos</a>
          <a class="btn btn-dark" href="{url_for("produto", slug=product["slug"])}">Ver no site</a>
        </article>
        """

    content = f"""
<section class="page-head">
 <div class="container">
  <span class="badge">Área reservada</span>
  <h1>Produtos e fotos</h1>
  <p class="lead">Adicione e organize as fotos que serão mostradas no site do Lab de Ideias.</p>
  <div class="actions">
   <a class="btn btn-dark" href="{url_for("painel")}">← Dashboard</a>
  </div>
 </div>
</section>
<section>
 <div class="container">
  <div class="grid">{cards}</div>
 </div>
</section>
"""
    return render_page("Produtos e fotos", content)

@app.route("/admin/produtos/<slug>/fotos", methods=["GET", "POST"])
@admin_required
def admin_fotos_produto(slug):
    product = product_by_slug(slug)
    if not product:
        abort(404)

    erro = ""
    if request.method == "POST":
        validar_csrf()
        arquivos = request.files.getlist("fotos")
        existentes = len(fotos_produto(slug))
        adicionadas = 0

        for arquivo in arquivos:
            if not arquivo or not arquivo.filename:
                continue
            if not extensao_permitida(arquivo.filename):
                erro = "Formato não permitido. Use JPG, JPEG, PNG, WEBP ou GIF."
                continue
            if existentes + adicionadas >= MAX_PRODUCT_PHOTOS:
                erro = f"O limite é de {MAX_PRODUCT_PHOTOS} fotos por categoria."
                break

            nome_seguro = secure_filename(arquivo.filename)
            if not nome_seguro:
                continue

            base_nome, ext = os.path.splitext(nome_seguro)
            nome_final = f"{slug}_{int(time.time() * 1000)}_{adicionadas}_{base_nome}{ext.lower()}"
            caminho = os.path.join(PRODUCT_UPLOAD_DIR, nome_final)
            arquivo.save(caminho)

            db = conectar()
            db.execute(
                "INSERT INTO produto_fotos (produto_slug, nome_arquivo) VALUES (?, ?)",
                (slug, nome_final)
            )
            db.commit()
            db.close()
            adicionadas += 1

        if not erro and adicionadas == 0:
            erro = "Selecione pelo menos uma imagem."

        if not erro:
            return redirect(url_for("admin_fotos_produto", slug=slug))

    fotos = fotos_produto(slug)
    erro_html = f'<div class="notice notice-error">{erro}</div><br>' if erro else ""
    photo_cards = "".join(
        f"""<div class="photo-admin-card">
          <img src="{url_for("foto_produto", filename=f["nome_arquivo"])}" alt="Foto de {product["name"]}">
          <form method="post" action="{url_for("admin_apagar_foto", photo_id=f["id"], slug=slug)}">
           <input type="hidden" name="csrf_token" value="{csrf()}">
           <button class="btn btn-dark" type="submit">🗑️ Apagar foto</button>
          </form>
        </div>"""
        for f in fotos
    )
    if not photo_cards:
        photo_cards = '<p class="muted">Ainda não existem fotos nesta categoria.</p>'

    content = f"""
<section class="page-head">
 <div class="container">
  <span class="badge">Gestão de produtos</span>
  <h1>{product["icon"]} {product["name"]}</h1>
  <p class="lead">Aqui podes colocar as fotos de {product["name"]}. Elas ficarão visíveis na página pública do produto.</p>
 </div>
</section>
<section>
 <div class="container">
  <div class="card">
   {erro_html}
   <div class="upload-box">
    <h2>📸 Adicionar fotos</h2>
    <p class="muted">Podes selecionar várias imagens de uma vez. Até {MAX_PRODUCT_PHOTOS} fotos por categoria.</p>
    <form method="post" enctype="multipart/form-data">
     <input type="hidden" name="csrf_token" value="{csrf()}">
     <label>Escolher fotos</label>
     <input type="file" name="fotos" accept="image/jpeg,image/png,image/webp,image/gif" multiple required>
     <button class="btn btn-gold" type="submit">📤 Publicar fotos</button>
    </form>
   </div>
  </div>
  <br>
  <div class="card">
   <h2>Fotos publicadas ({len(fotos)})</h2>
   <div class="photo-admin-grid">{photo_cards}</div>
  </div>
  <br>
  <a class="btn btn-dark" href="{url_for("admin_produtos")}">← Voltar aos produtos</a>
 </div>
</section>
"""
    return render_page(f"Fotos | {product['name']}", content)

@app.route("/admin/produtos/foto/<int:photo_id>/apagar/<slug>", methods=["POST"])
@admin_required
def admin_apagar_foto(photo_id, slug):
    validar_csrf()
    db = conectar()
    foto = db.execute(
        "SELECT nome_arquivo FROM produto_fotos WHERE id = ? AND produto_slug = ?",
        (photo_id, slug)
    ).fetchone()
    if foto:
        db.execute("DELETE FROM produto_fotos WHERE id = ?", (photo_id,))
        db.commit()
    db.close()

    if foto:
        caminho = os.path.join(PRODUCT_UPLOAD_DIR, os.path.basename(foto["nome_arquivo"]))
        if os.path.isfile(caminho):
            try:
                os.remove(caminho)
            except OSError:
                pass

    return redirect(url_for("admin_fotos_produto", slug=slug))

@app.route("/admin/pedido/<int:order_id>/estado", methods=["POST"])
@admin_required
def atualizar_estado(order_id):
    validar_csrf()

    estado = request.form.get("estado", "").strip()
    if estado not in STATES:
        abort(400)

    db = conectar()
    cur = db.cursor()
    cur.execute("UPDATE pedidos SET estado = ? WHERE id = ?", (estado, order_id))
    db.commit()
    db.close()

    return redirect(url_for("painel"))

@app.route("/admin/sair")
def admin_sair():
    session.pop("admin", None)
    return redirect(url_for("admin"))

# ============================================================
# LAB MANAGER NO SITE
# ============================================================

@app.route("/lab-manager")
def lab_manager():
    content = """
<section class="page-head">
  <div class="container">
    <span class="badge">Assistente do Lab de Ideias</span>
    <h1>🤖 Lab <span class="gold">Manager</span></h1>
    <p class="lead">Conversa com visitantes, responde perguntas e trabalha com os dados do Lab de Ideias.</p>
  </div>
</section>
<section>
  <div class="container ai-shell">
    <div class="card">
      <div class="ai-controls">
        <label>Idioma
          <select id="ai-language">
            <option value="pt">🇵🇹 Português</option>
            <option value="en">🇬🇧 English</option>
            <option value="fr">🇫🇷 Français</option>
            <option value="es">🇪🇸 Español</option>
          </select>
        </label>
        <label>Voz
          <select id="ai-voice-mode">
            <option value="auto">🎙️ Automática</option>
            <option value="male">♂️ Masculina</option>
            <option value="female">♀️ Feminina</option>
          </select>
        </label>
      </div>
      <div id="ai-chat" class="ai-chat">
        <div class="ai-msg ai-bot">Olá! 👋 Sou o Lab Manager, assistente do Lab de Ideias. Podes conversar comigo, pedir informações, análises, métricas, relatórios ou ajuda para escolher um serviço.</div>
      </div>
      <div class="ai-tools">
        <button type="button" onclick="aiQuick('Quais serviços o Lab de Ideias oferece?')">💼 Serviços</button>
        <button type="button" onclick="aiQuick('Quais são os preços dos serviços?')">💰 Preços</button>
        <button type="button" onclick="aiQuick('Como posso ajudar o meu negócio a crescer?')">📈 Estratégia</button>
      </div>
      <div class="ai-compose">
        <textarea id="ai-input" placeholder="Pergunte algo ao Lab Manager..." onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();aiSend()}"></textarea>
        <button class="btn btn-gold" type="button" onclick="aiSend()">➤</button>
      </div>
      <div class="ai-controls">
        <button class="btn btn-dark" type="button" onclick="aiListen()">🎙️ Falar</button>
        <button class="btn btn-dark" type="button" onclick="aiStopVoice()">🔇 Parar voz</button>
      </div>
      <div id="ai-status" class="ai-status">Online • pronto para conversar</div>
    </div>
  </div>
</section>
<script>
const aiChat=document.getElementById('ai-chat'), aiInput=document.getElementById('ai-input'), aiStatus=document.getElementById('ai-status');
function aiAdd(text,who){const d=document.createElement('div');d.className='ai-msg '+(who==='user'?'ai-user':'ai-bot');d.textContent=text;aiChat.appendChild(d);aiChat.scrollTop=aiChat.scrollHeight}
function aiQuick(t){aiInput.value=t;aiSend()}
async function aiSend(){const p=aiInput.value.trim();if(!p)return;aiAdd(p,'user');aiInput.value='';aiStatus.textContent='🧠 A processar...';try{const r=await fetch('/lab-manager/perguntar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pergunta:p,idioma:document.getElementById('ai-language').value})});const data=await r.json();const resposta=data.resposta||'Não consegui responder neste momento.';aiAdd(resposta,'bot');aiSpeak(resposta);aiStatus.textContent='Online • pronto para a próxima tarefa'}catch(e){aiAdd('Não consegui contactar o Lab Manager neste momento.','bot');aiStatus.textContent='Erro de comunicação'}}
function aiSpeak(text){if(!('speechSynthesis'in window)||!text)return;speechSynthesis.cancel();const lang=document.getElementById('ai-language').value;const u=new SpeechSynthesisUtterance(text);u.lang=lang==='pt'?'pt-PT':lang==='fr'?'fr-FR':lang==='es'?'es-ES':'en-US';const mode=document.getElementById('ai-voice-mode').value;const vs=speechSynthesis.getVoices().filter(v=>v.lang.toLowerCase().startsWith(lang));if(vs.length){if(mode==='female'){u.voice=vs.find(v=>/female|zira|samantha|susan|anna|amelie|monica/i.test(v.name))||vs[0]}else if(mode==='male'){u.voice=vs.find(v=>/male|david|daniel|jorge|thomas|lucas/i.test(v.name))||vs[0]}else u.voice=vs[0]}speechSynthesis.speak(u)}
function aiStopVoice(){if('speechSynthesis'in window)speechSynthesis.cancel()}
function aiListen(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){aiStatus.textContent='O reconhecimento de voz não é suportado neste navegador.';return}const r=new SR(),lang=document.getElementById('ai-language').value;r.lang=lang==='pt'?'pt-PT':lang==='fr'?'fr-FR':lang==='es'?'es-ES':'en-US';r.interimResults=false;r.onstart=()=>aiStatus.textContent='🎙️ A ouvir...';r.onresult=e=>{aiInput.value=e.results[0][0].transcript;aiSend()};r.onerror=()=>aiStatus.textContent='Não foi possível usar o microfone.';r.onend=()=>{if(aiStatus.textContent==='🎙️ A ouvir...')aiStatus.textContent='Online • pronto para conversar'};r.start()}
</script>
"""
    return render_page("Lab Manager", content)

@app.route("/lab-manager/perguntar", methods=["POST"])
def lab_manager_perguntar():
    try:
        dados=request.get_json(silent=True) or {}
        pergunta=str(dados.get("pergunta","")).strip()
        idioma=str(dados.get("idioma","pt")).strip().lower()
        if not pergunta:
            return jsonify({"resposta":"Escreve uma pergunta primeiro."})
        return jsonify({"resposta":lab_manager_responder(pergunta, idioma)})
    except Exception as erro:
        print("ERRO NO LAB MANAGER INTEGRADO:", erro)
        return jsonify({"resposta":"O Lab Manager encontrou um erro ao processar a mensagem."}), 500

# ============================================================
# ERROS
# ============================================================

@app.errorhandler(400)
def erro_400(error):
    return render_page("Erro 400", """
    <section class="page-head">
      <div class="container">
       <h1>Pedido inválido</h1>
       <p class="lead">Os dados enviados não puderam ser processados.</p>
       <a class="btn btn-gold" href="/">Voltar ao site</a>
      </div>
    </section>
    """), 400

@app.errorhandler(404)
def erro_404(error):
    return render_page("Página não encontrada", """
    <section class="page-head">
      <div class="container">
       <h1>404</h1>
       <p class="lead">Esta página não existe.</p>
       <a class="btn btn-gold" href="/">Voltar ao início</a>
      </div>
    </section>
    """), 404

# ============================================================
# EXECUTAR
# ============================================================

if __name__ == "__main__":
    carregar_lab_manager()
    print("============================================================")
    print("LAB DE IDEIAS | SITE")
    print("============================================================")
    print("Servidor: http://127.0.0.1:5000")
    print("Dashboard: http://127.0.0.1:5000/admin")
    print("Utilizador admin:", ADMIN_USER)
    print("Senha admin inicial:", ADMIN_PASSWORD)
    print("Localização:", LOCATION)
    print("============================================================")
    app.run(host="0.0.0.0", port=5000, debug=False)
