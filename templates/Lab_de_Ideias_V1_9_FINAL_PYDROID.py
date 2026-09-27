from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
import sqlite3
import os

from flask import Flask, request, redirect, url_for, session, flash, render_template_string, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ============================================================
# LAB DE IDEIAS • V1.0 → V1.9 • BASE LIMPA PARA PYDROID 3
# ============================================================
# Esta é uma única aplicação cumulativa:
# V1.0 base
# V1.1 planos + teste grátis
# V1.2 perfis
# V1.3 empresas
# V1.4 explorar
# V1.5 publicações
# V1.6 oportunidades
# V1.7 afiliados
# V1.8 notificações
# V1.9 pesquisa
#
# Importante:
# - Login e registo são mantidos simples e independentes dos módulos.
# - A base de dados desta reconstrução é NOVA: data/lab_de_ideias_v1_9.db
# - Não usa a base antiga lab.db, para evitar herdar esquemas quebrados.
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
PROFILE_DIR = UPLOAD_DIR / "profiles"
COMPANY_DIR = UPLOAD_DIR / "companies"
POST_DIR = UPLOAD_DIR / "posts"
DATA_DIR.mkdir(exist_ok=True)
for d in (PROFILE_DIR, COMPANY_DIR, POST_DIR):
    d.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "lab_de_ideias_v1_9.db"

app = Flask(__name__)
app.secret_key = os.environ.get("LAB_SECRET_KEY", "lab-de-ideias-v19-local-secret")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

PLANS = {
    "person": ("Pessoal", 3500),
    "micro": ("Microempresa", 7500),
    "small": ("Pequena empresa", 15000),
    "medium": ("Média empresa", 60000),
    "large": ("Grande empresa", 75000),
}

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def init_db():
    con = db()
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        user_type TEXT NOT NULL DEFAULT 'person',
        location TEXT DEFAULT '',
        bio TEXT DEFAULT '',
        profile_photo TEXT DEFAULT '',
        skills TEXT DEFAULT '',
        services TEXT DEFAULT '',
        instagram TEXT DEFAULT '',
        facebook TEXT DEFAULT '',
        whatsapp TEXT DEFAULT '',
        portfolio TEXT DEFAULT '',
        about TEXT DEFAULT '',
        availability TEXT DEFAULT '',
        business_size TEXT DEFAULT '',
        plan TEXT DEFAULT 'person',
        trial_started_at TEXT NOT NULL,
        trial_ends_at TEXT NOT NULL,
        subscription_status TEXT DEFAULT 'trial',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        category TEXT DEFAULT '',
        location TEXT DEFAULT '',
        description TEXT DEFAULT '',
        logo TEXT DEFAULT '',
        website TEXT DEFAULT '',
        whatsapp TEXT DEFAULT '',
        instagram TEXT DEFAULT '',
        facebook TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        company_id INTEGER,
        kind TEXT NOT NULL DEFAULT 'product',
        name TEXT NOT NULL,
        category TEXT DEFAULT '',
        description TEXT DEFAULT '',
        price TEXT DEFAULT '',
        image TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        company_id INTEGER,
        title TEXT NOT NULL,
        opportunity_type TEXT DEFAULT 'Emprego',
        category TEXT DEFAULT '',
        location TEXT DEFAULT '',
        description TEXT DEFAULT '',
        contact TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        image TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(author_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS post_likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(post_id, user_id),
        FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS affiliates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        code TEXT NOT NULL UNIQUE,
        clicks INTEGER DEFAULT 0,
        conversions INTEGER DEFAULT 0,
        commission REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS affiliate_clicks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        affiliate_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(affiliate_id) REFERENCES affiliates(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        kind TEXT DEFAULT 'system',
        link TEXT DEFAULT '',
        is_read INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        query TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
    );
    """)

    admin = cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)",
                        ("admin@labdeideias.local",)).fetchone()
    if not admin:
        start = datetime.now()
        end = start + timedelta(days=3650)
        cur.execute("""
            INSERT INTO users
            (name,email,password_hash,user_type,location,plan,trial_started_at,trial_ends_at,subscription_status)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            "Administrador", "admin@labdeideias.local",
            generate_password_hash("admin123"), "admin", "Angola",
            "large", start.isoformat(), end.isoformat(), "active"
        ))
    con.commit()
    con.close()

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    con = db()
    row = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    con.close()
    return row

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Inicia sessão para continuar.", "error")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u or u["user_type"] != "admin":
            flash("Área reservada ao administrador.", "error")
            return redirect(url_for("home"))
        return fn(*args, **kwargs)
    return wrapper

def notify(user_id, title, message, link=""):
    con = db()
    con.execute(
        "INSERT INTO notifications(user_id,title,message,kind,link) VALUES(?,?,?,?,?)",
        (user_id, title, message, "system", link)
    )
    con.commit()
    con.close()

def trial_info(user):
    if not user:
        return None
    try:
        end = datetime.fromisoformat(user["trial_ends_at"])
        days = max(0, (end.date() - datetime.now().date()).days)
    except Exception:
        days = 0
    return days

def plan_label(plan):
    return PLANS.get(plan, ("Plano", 0))[0]

def safe_next(default="dashboard"):
    nxt = request.args.get("next") or request.form.get("next")
    if nxt and nxt.startswith("/"):
        return nxt
    return url_for(default)

@app.context_processor
def inject_globals():
    u = current_user()
    unread = 0
    if u:
        con = db()
        unread = con.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
            (u["id"],)
        ).fetchone()[0]
        con.close()
    return {"me": u, "unread": unread, "trial_days": trial_info(u)}

STYLE = """
:root{--gold:#d4af37;--gold2:#f2d675;--black:#070707;--card:#111;--white:#fff;--muted:#a7a7a7;--line:#292929;--danger:#ff6b6b;--ok:#73e6a2}
*{box-sizing:border-box}body{margin:0;background:#080808;color:#f4f4f4;font-family:Arial,Helvetica,sans-serif;line-height:1.5}
a{color:inherit;text-decoration:none}.wrap{width:min(1120px,94%);margin:auto}
header{position:sticky;top:0;z-index:10;background:rgba(5,5,5,.97);border-bottom:1px solid #222}
.nav{min-height:76px;display:flex;align-items:center;gap:22px;overflow-x:auto}.brand{font-size:25px;font-weight:800;white-space:nowrap}.brand span{color:var(--gold)}
.nav a{color:#ddd;white-space:nowrap}.nav a:hover{color:var(--gold2)}
.hero{padding:60px 0 35px}.hero h1{font-size:clamp(38px,7vw,72px);line-height:1;margin:10px 0}.gold{color:var(--gold)}.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}.card{background:linear-gradient(145deg,#151515,#0d0d0d);border:1px solid #292929;border-radius:18px;padding:20px}.card h3{margin-top:0}
.btn{display:inline-block;border:1px solid #444;background:#171717;color:#fff;padding:11px 16px;border-radius:10px;cursor:pointer}.btn.gold{background:var(--gold);color:#090909;border-color:var(--gold);font-weight:800}.btn.danger{border-color:#633;background:#211010}
form{display:grid;gap:12px}input,textarea,select{width:100%;background:#090909;border:1px solid #393939;color:#fff;border-radius:10px;padding:13px;font:inherit}textarea{min-height:120px;resize:vertical}
label{font-weight:700}.form-card{max-width:650px;margin:35px auto}.flash{padding:14px;border-radius:10px;margin:12px 0;border:1px solid #444}.flash.error{border-color:#733;background:#241010}.flash.success{border-color:#375;background:#102117}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}.stat{padding:18px;border:1px solid #292929;border-radius:15px;background:#101010}.stat b{font-size:28px;color:var(--gold)}
.badge{display:inline-block;padding:4px 9px;border-radius:99px;background:#211d0e;color:var(--gold2);font-size:12px}
.search{display:flex;gap:8px}.search input{flex:1}
img.media{width:100%;max-height:320px;object-fit:cover;border-radius:12px;border:1px solid #292929}
footer{margin-top:70px;padding:35px 0;border-top:1px solid #222;color:#888}
.small{font-size:13px}.actions{display:flex;gap:8px;flex-wrap:wrap}.space{height:20px}
@media(max-width:700px){.nav{gap:14px}.brand{font-size:20px}.hero{padding-top:35px}.search{flex-direction:column}.btn{width:100%;text-align:center}}
"""

BASE = """<!doctype html><html lang="pt"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }} • Lab de Ideias</title><style>""" + STYLE + """</style></head><body>
<header><div class="wrap nav"><a class="brand" href="{{ url_for('home') }}">Lab <span>de</span> Ideias</a>
<a href="{{ url_for('home') }}">Início</a><a href="{{ url_for('explorar') }}">Explorar</a><a href="{{ url_for('publicacoes') }}">Publicações</a><a href="{{ url_for('oportunidades') }}">Oportunidades</a><a href="{{ url_for('planos') }}">Planos</a>
{% if me %}<a href="{{ url_for('notificacoes') }}">Notificações{% if unread %} ({{ unread }}){% endif %}</a><a href="{{ url_for('dashboard') }}">Dashboard</a><a href="{{ url_for('logout') }}">Sair</a>{% else %}<a href="{{ url_for('login') }}">Entrar</a><a class="btn gold" href="{{ url_for('registo') }}">Criar conta</a>{% endif %}
</div></header><main class="wrap">
{% with msgs=get_flashed_messages(with_categories=true) %}{% for cat,msg in msgs %}<div class="flash {{cat}}">{{msg}}</div>{% endfor %}{% endwith %}
{{ body|safe }}</main><footer><div class="wrap">Lab de Ideias • Uma plataforma para pessoas, empresas e oportunidades.</div></footer></body></html>"""

def page(title, body):
    return render_template_string(BASE, title=title, body=body)

@app.route("/")
def home():
    con = db()
    posts = con.execute("""
        SELECT p.*,u.name FROM posts p JOIN users u ON u.id=p.author_id
        ORDER BY p.id DESC LIMIT 6
    """).fetchall()
    opps = con.execute("SELECT * FROM opportunities ORDER BY id DESC LIMIT 6").fetchall()
    con.close()
    body = render_template_string("""
    <section class="hero">
      <span class="badge">Lab de Ideias</span>
      <h1>Onde ideias encontram <span class="gold">oportunidades.</span></h1>
      <p class="muted">Uma plataforma para pessoas, empresas e oportunidades.</p>
      <form class="search" method="get" action="{{url_for('pesquisar')}}">
        <input name="q" placeholder="Pesquisar pessoas, empresas, serviços, produtos, oportunidades..." required>
        <button class="btn gold">Pesquisar</button>
      </form>
      <div class="space"></div>
      <div class="actions"><a class="btn gold" href="{{url_for('registo')}}">Começar grátis</a><a class="btn" href="{{url_for('explorar')}}">Explorar</a></div>
    </section>
    <section><h2>Publicações recentes</h2><div class="grid">{% for p in posts %}<article class="card"><b>{{p.name}}</b><p>{{p.content}}</p><span class="small muted">{{p.created_at}}</span></article>{% else %}<div class="card">Ainda não existem publicações.</div>{% endfor %}</div></section>
    <div class="space"></div>
    <section><h2>Oportunidades</h2><div class="grid">{% for o in opps %}<article class="card"><span class="badge">{{o.opportunity_type}}</span><h3>{{o.title}}</h3><p>{{o.description}}</p><span class="small muted">{{o.location}}</span></article>{% else %}<div class="card">Ainda não existem oportunidades.</div>{% endfor %}</div></section>
    """, posts=posts, opps=opps)
    return page("Início", body)

@app.route("/registo", methods=["GET","POST"])
def registo():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        typ = request.form.get("user_type","person")
        location = request.form.get("location","").strip()
        size = request.form.get("business_size","").strip()
        if typ not in ("person","company"):
            typ = "person"
        plan = "person" if typ == "person" else (size if size in ("micro","small","medium","large") else "micro")
        if not name or not email or len(password) < 6:
            flash("Preenche nome, email e uma senha com pelo menos 6 caracteres.", "error")
            return redirect(url_for("registo"))
        con = db()
        try:
            start = datetime.now()
            end = start + timedelta(days=15)
            cur = con.cursor()
            cur.execute("""
                INSERT INTO users(name,email,password_hash,user_type,location,business_size,plan,trial_started_at,trial_ends_at,subscription_status)
                VALUES(?,?,?,?,?,?,?,?,?,?)
            """, (name,email,generate_password_hash(password),typ,location,size,plan,start.isoformat(),end.isoformat(),"trial"))
            uid = cur.lastrowid
            if typ == "company":
                cur.execute("""
                    INSERT INTO companies(owner_id,name,location,description)
                    VALUES(?,?,?,?)
                """, (uid,name,location,"Perfil empresarial em construção."))
            con.commit()
            con.close()
            flash("Conta criada com sucesso. Tens 15 dias grátis.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            con.rollback(); con.close()
            flash("Este email já está registado.", "error")
        except Exception as e:
            con.rollback(); con.close()
            flash("Não foi possível criar a conta. Verifica os dados e tenta novamente.", "error")
            print("ERRO REGISTO:", repr(e))
    body = render_template_string("""
    <div class="form-card card"><h1>Cria a tua conta.</h1><p class="muted">Toda conta começa com <b>15 dias grátis</b>.</p>
    <form method="post">
      <label>Nome</label><input name="name" required>
      <label>Email</label><input type="email" name="email" required>
      <label>Senha</label><input type="password" name="password" minlength="6" required>
      <label>Tipo de conta</label><select name="user_type" id="ut" onchange="toggleSize()"><option value="person">Pessoa</option><option value="company">Empresa</option></select>
      <div id="sizebox" style="display:none"><label>Tamanho da empresa</label><select name="business_size"><option value="micro">Microempresa</option><option value="small">Pequena empresa</option><option value="medium">Média empresa</option><option value="large">Grande empresa</option></select></div>
      <label>Localização</label><input name="location" placeholder="Ex.: Moçâmedes, Namibe">
      <button class="btn gold">Criar conta</button>
    </form></div>
    <script>function toggleSize(){document.getElementById('sizebox').style.display=document.getElementById('ut').value==='company'?'block':'none'}</script>
    """)
    return page("Criar conta", body)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        con = db()
        user = con.execute("SELECT * FROM users WHERE lower(email)=?", (email,)).fetchone()
        con.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash("Sessão iniciada.", "success")
            return redirect(url_for("dashboard"))
        flash("Email ou senha incorretos.", "error")
    body = render_template_string("""
    <div class="form-card card"><h1>Entrar</h1><form method="post">
      <label>Email</label><input type="email" name="email" required>
      <label>Senha</label><input type="password" name="password" required>
      <button class="btn gold">Entrar</button>
    </form><p class="muted">Admin inicial: admin@labdeideias.local / admin123</p></div>
    """)
    return page("Entrar", body)

@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão terminada.", "success")
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    u = current_user()
    con = db()
    counts = {
        "posts": con.execute("SELECT COUNT(*) FROM posts WHERE author_id=?", (u["id"],)).fetchone()[0],
        "listings": con.execute("SELECT COUNT(*) FROM listings WHERE owner_id=?", (u["id"],)).fetchone()[0],
        "opps": con.execute("SELECT COUNT(*) FROM opportunities WHERE owner_id=?", (u["id"],)).fetchone()[0],
        "notifs": con.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",(u["id"],)).fetchone()[0],
    }
    company = con.execute("SELECT * FROM companies WHERE owner_id=? ORDER BY id DESC LIMIT 1",(u["id"],)).fetchone()
    con.close()
    body = render_template_string("""
    <section class="hero"><span class="badge">{{u.user_type}}</span><h1>Olá, {{u.name}}.</h1><p class="muted">Plano: <b>{{plan_label(u.plan)}}</b> • {{trial_days}} dias de teste restantes.</p></section>
    <div class="stats"><div class="stat"><b>{{counts.posts}}</b><br>Publicações</div><div class="stat"><b>{{counts.listings}}</b><br>Produtos/Serviços</div><div class="stat"><b>{{counts.opps}}</b><br>Oportunidades</div><div class="stat"><b>{{counts.notifs}}</b><br>Notificações</div></div>
    <div class="space"></div><div class="grid">
      <a class="card" href="{{url_for('perfil',uid=u.id)}}"><h3>👤 Meu perfil</h3><p class="muted">Editar e apresentar a tua presença profissional.</p></a>
      <a class="card" href="{{url_for('publicacoes')}}"><h3>📢 Publicações</h3><p class="muted">Partilhar ideias e conteúdos.</p></a>
      <a class="card" href="{{url_for('oportunidades')}}"><h3>🎯 Oportunidades</h3><p class="muted">Explorar oportunidades.</p></a>
      <a class="card" href="{{url_for('afiliados')}}"><h3>🔗 Afiliados</h3><p class="muted">Criar o teu código de afiliado.</p></a>
      {% if company %}<a class="card" href="{{url_for('empresa',cid=company.id)}}"><h3>🏢 Minha empresa</h3><p class="muted">{{company.name}}</p></a>{% endif %}
    </div>
    """, u=u, counts=counts, company=company, plan_label=plan_label)
    return page("Dashboard", body)

@app.route("/perfil/<int:uid>", methods=["GET","POST"])
def perfil(uid):
    con = db()
    user = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        con.close(); return "Utilizador não encontrado", 404
    if request.method == "POST":
        me = current_user()
        if not me or me["id"] != uid:
            con.close(); flash("Só podes editar o teu próprio perfil.", "error"); return redirect(url_for("perfil",uid=uid))
        fields = ("name","location","bio","skills","services","instagram","facebook","whatsapp","portfolio","about","availability")
        vals = [request.form.get(f,"").strip() for f in fields]
        con.execute("""UPDATE users SET name=?,location=?,bio=?,skills=?,services=?,instagram=?,facebook=?,whatsapp=?,portfolio=?,about=?,availability=? WHERE id=?""", (*vals,uid))
        con.commit()
        user = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        flash("Perfil atualizado.", "success")
    posts = con.execute("SELECT * FROM posts WHERE author_id=? ORDER BY id DESC LIMIT 6",(uid,)).fetchall()
    listings = con.execute("SELECT * FROM listings WHERE owner_id=? ORDER BY id DESC LIMIT 6",(uid,)).fetchall()
    con.close()
    editable = current_user() and current_user()["id"] == uid
    body = render_template_string("""
    <section class="hero"><span class="badge">Perfil</span><h1>{{user.name}}</h1><p class="muted">{{user.location}}</p><p>{{user.bio}}</p></section>
    <div class="grid"><div class="card"><h3>Competências</h3><p>{{user.skills or 'Ainda não definido.'}}</p></div><div class="card"><h3>Serviços</h3><p>{{user.services or 'Ainda não definido.'}}</p></div><div class="card"><h3>Disponibilidade</h3><p>{{user.availability or 'Ainda não definido.'}}</p></div></div>
    {% if editable %}<div class="space"></div><div class="form-card card"><h2>Editar perfil</h2><form method="post">
      {% for f,label in fields %}<label>{{label}}</label><textarea name="{{f}}" {% if f in ['name','location'] %}style="min-height:55px"{% endif %}>{{user[f] or ''}}</textarea>{% endfor %}
      <button class="btn gold">Guardar</button></form></div>{% endif %}
    <div class="space"></div><h2>Publicações</h2><div class="grid">{% for p in posts %}<div class="card"><p>{{p.content}}</p></div>{% else %}<div class="card">Sem publicações.</div>{% endfor %}</div>
    <div class="space"></div><h2>Produtos e serviços</h2><div class="grid">{% for x in listings %}<div class="card"><span class="badge">{{x.kind}}</span><h3>{{x.name}}</h3><p>{{x.description}}</p><b>{{x.price}}</b></div>{% else %}<div class="card">Nenhum item.</div>{% endfor %}</div>
    """, user=user, posts=posts, listings=listings, editable=editable,
       fields=[("name","Nome"),("location","Localização"),("bio","Bio"),("skills","Competências"),("services","Serviços"),("instagram","Instagram"),("facebook","Facebook"),("whatsapp","WhatsApp"),("portfolio","Portfólio"),("about","Sobre"),("availability","Disponibilidade")])
    return page("Perfil", body)

@app.route("/empresa/<int:cid>")
def empresa(cid):
    con = db()
    company = con.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    if not company:
        con.close(); return "Empresa não encontrada",404
    owner = con.execute("SELECT id,name FROM users WHERE id=?",(company["owner_id"],)).fetchone()
    listings = con.execute("SELECT * FROM listings WHERE company_id=? ORDER BY id DESC",(cid,)).fetchall()
    opps = con.execute("SELECT * FROM opportunities WHERE company_id=? ORDER BY id DESC",(cid,)).fetchall()
    con.close()
    body = render_template_string("""
    <section class="hero"><span class="badge">Empresa</span><h1>{{company.name}}</h1><p class="muted">{{company.category}} • {{company.location}}</p><p>{{company.description}}</p></section>
    <div class="grid"><div class="card"><h3>Produtos e serviços</h3>{% for x in listings %}<p><b>{{x.name}}</b> • {{x.price}}</p>{% else %}<p class="muted">Nenhum item.</p>{% endfor %}</div>
    <div class="card"><h3>Oportunidades</h3>{% for o in opps %}<p><b>{{o.title}}</b><br>{{o.description}}</p>{% else %}<p class="muted">Nenhuma oportunidade.</p>{% endfor %}</div></div>
    """,company=company,owner=owner,listings=listings,opps=opps)
    return page("Empresa", body)

@app.route("/empresa/<int:cid>/editar", methods=["GET","POST"])
@login_required
def editar_empresa(cid):
    me=current_user()
    con=db()
    company=con.execute("SELECT * FROM companies WHERE id=? AND owner_id=?",(cid,me["id"])).fetchone()
    if not company:
        con.close(); return "Empresa não encontrada",404
    if request.method=="POST":
        vals=(request.form.get("name","").strip(),request.form.get("category","").strip(),request.form.get("location","").strip(),request.form.get("description","").strip(),request.form.get("website","").strip(),request.form.get("whatsapp","").strip(),request.form.get("instagram","").strip(),request.form.get("facebook","").strip(),cid)
        con.execute("""UPDATE companies SET name=?,category=?,location=?,description=?,website=?,whatsapp=?,instagram=?,facebook=? WHERE id=?""",vals)
        con.commit(); con.close(); flash("Empresa atualizada.","success"); return redirect(url_for("empresa",cid=cid))
    con.close()
    body=render_template_string("""<div class="form-card card"><h1>Editar empresa</h1><form method="post">
    <label>Nome</label><input name="name" value="{{c.name}}" required><label>Categoria</label><input name="category" value="{{c.category}}">
    <label>Localização</label><input name="location" value="{{c.location}}"><label>Descrição</label><textarea name="description">{{c.description}}</textarea>
    <label>Website</label><input name="website" value="{{c.website}}"><label>WhatsApp</label><input name="whatsapp" value="{{c.whatsapp}}">
    <label>Instagram</label><input name="instagram" value="{{c.instagram}}"><label>Facebook</label><input name="facebook" value="{{c.facebook}}">
    <button class="btn gold">Guardar</button></form></div>""",c=company)
    return page("Editar empresa",body)

@app.route("/publicacoes", methods=["GET","POST"])
def publicacoes():
    if request.method=="POST":
        me=current_user()
        if not me:
            flash("Entra na tua conta para publicar.","error"); return redirect(url_for("login"))
        content=request.form.get("content","").strip()
        if content:
            con=db(); con.execute("INSERT INTO posts(author_id,content) VALUES(?,?)",(me["id"],content)); con.commit(); con.close()
            flash("Publicação criada.","success")
        return redirect(url_for("publicacoes"))
    con=db()
    posts=con.execute("""SELECT p.*,u.name,(SELECT COUNT(*) FROM post_likes l WHERE l.post_id=p.id) likes FROM posts p JOIN users u ON u.id=p.author_id ORDER BY p.id DESC""").fetchall()
    con.close()
    body=render_template_string("""<section class="hero"><h1>Publicações</h1><p class="muted">Ideias, conteúdos e descobertas da comunidade.</p></section>
    {% if me %}<div class="card"><form method="post"><textarea name="content" placeholder="Partilha uma ideia..." required></textarea><button class="btn gold">Publicar</button></form></div><div class="space"></div>{% endif %}
    <div class="grid">{% for p in posts %}<article class="card"><h3>{{p.name}}</h3><p>{{p.content}}</p><div class="actions"><form method="post" action="{{url_for('like_post',pid=p.id)}}"><button class="btn">♡ {{p.likes}}</button></form></div><span class="small muted">{{p.created_at}}</span></article>{% else %}<div class="card">Ainda não há publicações.</div>{% endfor %}</div>""",posts=posts)
    return page("Publicações",body)

@app.route("/publicacao/<int:pid>/like",methods=["POST"])
@login_required
def like_post(pid):
    me=current_user(); con=db()
    try:
        con.execute("INSERT INTO post_likes(post_id,user_id) VALUES(?,?)",(pid,me["id"]))
        con.commit()
    except sqlite3.IntegrityError:
        con.execute("DELETE FROM post_likes WHERE post_id=? AND user_id=?",(pid,me["id"])); con.commit()
    con.close()
    return redirect(request.referrer or url_for("publicacoes"))

@app.route("/oportunidades", methods=["GET","POST"])
def oportunidades():
    if request.method=="POST":
        me=current_user()
        if not me:
            flash("Entra na tua conta para publicar uma oportunidade.","error"); return redirect(url_for("login"))
        title=request.form.get("title","").strip(); desc=request.form.get("description","").strip()
        if not title or not desc:
            flash("Título e descrição são obrigatórios.","error"); return redirect(url_for("oportunidades"))
        con=db(); company=con.execute("SELECT id FROM companies WHERE owner_id=? ORDER BY id DESC LIMIT 1",(me["id"],)).fetchone()
        con.execute("""INSERT INTO opportunities(owner_id,company_id,title,opportunity_type,category,location,description,contact) VALUES(?,?,?,?,?,?,?,?)""",
                    (me["id"],company["id"] if company else None,title,request.form.get("opportunity_type","Emprego"),request.form.get("category",""),request.form.get("location",""),desc,request.form.get("contact","")))
        con.commit(); con.close(); flash("Oportunidade publicada.","success"); return redirect(url_for("oportunidades"))
    con=db(); rows=con.execute("SELECT o.*,u.name, c.name company_name FROM opportunities o JOIN users u ON u.id=o.owner_id LEFT JOIN companies c ON c.id=o.company_id ORDER BY o.id DESC").fetchall(); con.close()
    body=render_template_string("""<section class="hero"><h1>Oportunidades</h1><p class="muted">Emprego, parceria, projeto, colaboração e outras oportunidades.</p></section>
    {% if me %}<div class="card"><h3>Publicar oportunidade</h3><form method="post"><input name="title" placeholder="Título" required><select name="opportunity_type"><option>Emprego</option><option>Parceria</option><option>Projeto</option><option>Freelance</option><option>Estágio</option></select><input name="category" placeholder="Categoria"><input name="location" placeholder="Localização"><textarea name="description" placeholder="Descrição" required></textarea><input name="contact" placeholder="Contacto"><button class="btn gold">Publicar</button></form></div><div class="space"></div>{% endif %}
    <div class="grid">{% for o in rows %}<article class="card"><span class="badge">{{o.opportunity_type}}</span><h3>{{o.title}}</h3><p>{{o.description}}</p><p class="muted">{{o.location}}{% if o.company_name %} • {{o.company_name}}{% endif %}</p><small>{{o.contact}}</small></article>{% else %}<div class="card">Nenhuma oportunidade encontrada.</div>{% endfor %}</div>""",rows=rows)
    return page("Oportunidades",body)

@app.route("/explorar")
def explorar():
    con=db()
    people=con.execute("SELECT id,name,location,skills,services FROM users WHERE user_type!='admin' ORDER BY id DESC LIMIT 12").fetchall()
    companies=con.execute("SELECT id,name,category,location FROM companies ORDER BY id DESC LIMIT 12").fetchall()
    items=con.execute("SELECT * FROM listings ORDER BY id DESC LIMIT 12").fetchall()
    con.close()
    body=render_template_string("""<section class="hero"><h1>Explorar</h1><p class="muted">Pessoas, empresas, produtos e serviços.</p></section>
    <h2>Pessoas</h2><div class="grid">{% for p in people %}<a class="card" href="{{url_for('perfil',uid=p.id)}}"><h3>{{p.name}}</h3><p>{{p.location}}</p><p class="muted">{{p.skills or p.services}}</p></a>{% endfor %}</div>
    <div class="space"></div><h2>Empresas</h2><div class="grid">{% for c in companies %}<a class="card" href="{{url_for('empresa',cid=c.id)}}"><h3>{{c.name}}</h3><p>{{c.category}} • {{c.location}}</p></a>{% endfor %}</div>
    <div class="space"></div><h2>Produtos e serviços</h2><div class="grid">{% for x in items %}<div class="card"><span class="badge">{{x.kind}}</span><h3>{{x.name}}</h3><p>{{x.description}}</p><b>{{x.price}}</b></div>{% endfor %}</div>""",people=people,companies=companies,items=items)
    return page("Explorar",body)

@app.route("/pesquisar")
def pesquisar():
    q=request.args.get("q","").strip()
    if not q:
        return redirect(url_for("home"))
    me=current_user()
    con=db()
    if me:
        con.execute("INSERT INTO searches(user_id,query) VALUES(?,?)",(me["id"],q)); con.commit()
    like=f"%{q}%"
    people=con.execute("SELECT id,name,location,bio,skills,services FROM users WHERE user_type!='admin' AND (name LIKE ? OR location LIKE ? OR bio LIKE ? OR skills LIKE ? OR services LIKE ?) LIMIT 30",(like,like,like,like,like)).fetchall()
    companies=con.execute("SELECT * FROM companies WHERE name LIKE ? OR category LIKE ? OR location LIKE ? OR description LIKE ? LIMIT 30",(like,like,like,like)).fetchall()
    items=con.execute("SELECT * FROM listings WHERE name LIKE ? OR category LIKE ? OR description LIKE ? LIMIT 30",(like,like,like)).fetchall()
    opps=con.execute("SELECT * FROM opportunities WHERE title LIKE ? OR category LIKE ? OR location LIKE ? OR description LIKE ? LIMIT 30",(like,like,like,like)).fetchall()
    posts=con.execute("SELECT p.*,u.name FROM posts p JOIN users u ON u.id=p.author_id WHERE p.content LIKE ? LIMIT 30",(like,)).fetchall()
    con.close()
    body=render_template_string("""<section class="hero"><h1>Pesquisa</h1><form class="search"><input name="q" value="{{q}}" required><button class="btn gold">Pesquisar</button></form></section>
    <h2>Pessoas ({{people|length}})</h2><div class="grid">{% for p in people %}<a class="card" href="{{url_for('perfil',uid=p.id)}}"><h3>{{p.name}}</h3><p>{{p.location}}</p><p>{{p.skills}}</p></a>{% else %}<div class="card">Nenhuma pessoa.</div>{% endfor %}</div>
    <div class="space"></div><h2>Empresas ({{companies|length}})</h2><div class="grid">{% for c in companies %}<a class="card" href="{{url_for('empresa',cid=c.id)}}"><h3>{{c.name}}</h3><p>{{c.category}} • {{c.location}}</p></a>{% else %}<div class="card">Nenhuma empresa.</div>{% endfor %}</div>
    <div class="space"></div><h2>Produtos/Serviços ({{items|length}})</h2><div class="grid">{% for x in items %}<div class="card"><h3>{{x.name}}</h3><p>{{x.description}}</p><b>{{x.price}}</b></div>{% else %}<div class="card">Nenhum resultado.</div>{% endfor %}</div>
    <div class="space"></div><h2>Oportunidades ({{opps|length}})</h2><div class="grid">{% for o in opps %}<div class="card"><h3>{{o.title}}</h3><p>{{o.description}}</p></div>{% else %}<div class="card">Nenhuma oportunidade.</div>{% endfor %}</div>
    <div class="space"></div><h2>Publicações ({{posts|length}})</h2><div class="grid">{% for p in posts %}<div class="card"><b>{{p.name}}</b><p>{{p.content}}</p></div>{% else %}<div class="card">Nenhuma publicação.</div>{% endfor %}</div>
    """,q=q,people=people,companies=companies,items=items,opps=opps,posts=posts)
    return page("Pesquisa",body)

@app.route("/afiliados",methods=["GET","POST"])
@login_required
def afiliados():
    me=current_user(); con=db()
    aff=con.execute("SELECT * FROM affiliates WHERE user_id=?",(me["id"],)).fetchone()
    if request.method=="POST" and not aff:
        code="LAB"+str(me["id"])+me["name"].replace(" ","").upper()[:4]
        try:
            con.execute("INSERT INTO affiliates(user_id,code) VALUES(?,?)",(me["id"],code))
            con.commit()
        except sqlite3.IntegrityError:
            code="LAB"+str(me["id"])+str(int(datetime.now().timestamp()))[-5:]
            con.execute("INSERT INTO affiliates(user_id,code) VALUES(?,?)",(me["id"],code)); con.commit()
        aff=con.execute("SELECT * FROM affiliates WHERE user_id=?",(me["id"],)).fetchone()
    con.close()
    body=render_template_string("""<div class="hero"><h1>Afiliados</h1><p class="muted">Participa no sistema de divulgação do Lab de Ideias.</p></div>
    {% if aff %}<div class="card"><h2>O teu código</h2><p class="gold">{{aff.code}}</p><p>Cliques: {{aff.clicks}} • Conversões: {{aff.conversions}} • Comissão: {{aff.commission}}</p><input readonly value="{{request.url_root}}af/{{aff.code}}"></div>{% else %}<div class="card"><p>Ainda não tens código de afiliado.</p><form method="post"><button class="btn gold">Criar código de afiliado</button></form></div>{% endif %}""",aff=aff)
    return page("Afiliados",body)

@app.route("/af/<code>")
def affiliate_redirect(code):
    con=db(); aff=con.execute("SELECT * FROM affiliates WHERE code=?",(code,)).fetchone()
    if not aff:
        con.close(); return redirect(url_for("home"))
    con.execute("UPDATE affiliates SET clicks=clicks+1 WHERE id=?",(aff["id"],))
    con.execute("INSERT INTO affiliate_clicks(affiliate_id) VALUES(?)",(aff["id"],))
    con.commit(); con.close()
    return redirect(url_for("registo"))

@app.route("/notificacoes")
@login_required
def notificacoes():
    me=current_user(); con=db()
    rows=con.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 100",(me["id"],)).fetchall()
    con.execute("UPDATE notifications SET is_read=1 WHERE user_id=?",(me["id"],)); con.commit(); con.close()
    body=render_template_string("""<section class="hero"><h1>Notificações</h1></section><div class="grid">{% for n in rows %}<div class="card"><h3>{{n.title}}</h3><p>{{n.message}}</p><small class="muted">{{n.created_at}}</small></div>{% else %}<div class="card">Não tens notificações.</div>{% endfor %}</div>""",rows=rows)
    return page("Notificações",body)

@app.route("/planos")
def planos():
    body=render_template_string("""<section class="hero"><h1>Planos</h1><p class="muted">Todas as contas começam com 15 dias de teste.</p></section>
    <div class="grid">{% for key,(name,price) in plans.items() %}<div class="card"><span class="badge">{{key}}</span><h2>{{name}}</h2><h3 class="gold">{{"{:,.0f}".format(price).replace(",", ".")}} Kz/mês</h3><p>Perfil, presença na plataforma e funcionalidades conforme a evolução do Lab.</p><a class="btn gold" href="{{url_for('registo')}}">Começar</a></div>{% endfor %}</div>""",plans=PLANS)
    return page("Planos",body)

@app.route("/admin")
@admin_required
def admin():
    con=db()
    users=con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    companies=con.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    posts=con.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    opps=con.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    con.close()
    body=render_template_string("""<section class="hero"><h1>Administração</h1></section><div class="stats"><div class="stat"><b>{{users}}</b><br>Utilizadores</div><div class="stat"><b>{{companies}}</b><br>Empresas</div><div class="stat"><b>{{posts}}</b><br>Publicações</div><div class="stat"><b>{{opps}}</b><br>Oportunidades</div></div>""",users=users,companies=companies,posts=posts,opps=opps)
    return page("Admin",body)

@app.route("/health")
def health():
    return {"status":"ok","app":"Lab de Ideias","version":"V1.9","database":str(DB_PATH.name)}

@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

init_db()

if __name__ == "__main__":
    print("="*55)
    print("LAB DE IDEIAS V1.9 • BASE COMPLETA PARA PYDROID 3")
    print("="*55)
    print("Local: http://127.0.0.1:5000")
    print("Admin: admin@labdeideias.local")
    print("Senha: admin123")
    print("Base nova:", DB_PATH)
    print("="*55)
    app.run(host="0.0.0.0", port=5000, debug=False)
