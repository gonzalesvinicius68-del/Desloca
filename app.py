from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
import sqlite3
import hashlib

app = Flask(__name__)
app.secret_key = "desloca_gestao_2024"
CORS(app)

DB_PATH = "database.db"

# ─────────────────────────────────────────────
# BANCO DE DADOS
# ─────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def criar_banco():
    conn = get_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS patinetes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_registro TEXT UNIQUE NOT NULL,
        lat REAL DEFAULT -23.5558,
        lng REAL DEFAULT -46.6396,
        bateria INTEGER DEFAULT 100,
        quilometragem REAL DEFAULT 0,
        status TEXT DEFAULT 'disponivel',
        ultima_manutencao TEXT,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS manutencoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patinete_id INTEGER NOT NULL,
        tipo TEXT NOT NULL,
        descricao TEXT,
        custo REAL DEFAULT 0,
        data TEXT NOT NULL,
        tecnico TEXT,
        FOREIGN KEY (patinete_id) REFERENCES patinetes(id)
    )""")

    # Admin padrão: email=admin@desloca.com  senha=admin123
    senha_padrao = hashlib.sha256("admin123".encode()).hexdigest()
    try:
        c.execute("INSERT INTO usuarios (nome, email, senha) VALUES (?,?,?)",
                  ("Administrador", "admin@desloca.com", senha_padrao))
    except sqlite3.IntegrityError:
        pass

    # Patinetes de exemplo
    c.execute("SELECT COUNT(*) FROM patinetes")
    if c.fetchone()[0] == 0:
        exemplos = [
            ("PAT-0001", -23.5505, -46.6333, 92, 145.3, "disponivel", "2024-03-10"),
            ("PAT-0002", -23.5620, -46.6550, 78, 230.1, "disponivel", "2024-02-28"),
            ("PAT-0003", -23.5490, -46.6420, 23, 412.7, "manutencao", "2024-01-15"),
            ("PAT-0004", -23.5710, -46.6300, 55, 89.0,  "disponivel", "2024-03-05"),
            ("PAT-0005", -23.5580, -46.6600, 8,  567.4, "alerta",     "2023-12-20"),
        ]
        c.executemany("""INSERT INTO patinetes
            (numero_registro, lat, lng, bateria, quilometragem, status, ultima_manutencao)
            VALUES (?,?,?,?,?,?,?)""", exemplos)

    conn.commit()
    conn.close()

# ─────────────────────────────────────────────
# PROTEÇÃO DE ROTA
# ─────────────────────────────────────────────
def login_requerido(f):
    from functools import wraps
    @wraps(f)
    def decorador(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorador

# ─────────────────────────────────────────────
# PÁGINAS HTML
# ─────────────────────────────────────────────
@app.route("/")
@login_requerido
def index():
    return render_template("dashboard.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/cadastro")
def cadastro_page():
    return render_template("cadastro.html")

@app.route("/patinetes")
@login_requerido
def patinetes_page():
    return render_template("patinetes.html")

@app.route("/manutencao")
@login_requerido
def manutencao_page():
    return render_template("manutencao.html")

# ─────────────────────────────────────────────
# API — AUTENTICAÇÃO
# ─────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json()
    senha_hash = hashlib.sha256(d["senha"].encode()).hexdigest()
    conn = get_db()
    u = conn.execute(
        "SELECT * FROM usuarios WHERE email=? AND senha=?",
        (d["email"], senha_hash)
    ).fetchone()
    conn.close()
    if u:
        session["usuario_id"] = u["id"]
        session["usuario_nome"] = u["nome"]
        return jsonify({"ok": True, "nome": u["nome"]})
    return jsonify({"erro": "Email ou senha incorretos"}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})
#
# cadastro
#
@app.route("/api/cadastro", methods=["POST"])
def cadastro():

    d = request.get_json()

    nome = d.get("nome")
    email = d.get("email")
    senha = d.get("senha")

    if not nome or not email or not senha:
        return jsonify({
            "erro": "Preencha todos os campos"
        }), 400

    senha_hash = hashlib.sha256(senha.encode()).hexdigest()

    conn = get_db()

    try:

        conn.execute("""
            INSERT INTO usuarios (nome, email, senha)
            VALUES (?, ?, ?)
        """, (nome, email, senha_hash))

        conn.commit()

        return jsonify({
            "ok": True,
            "mensagem": "Usuário criado com sucesso"
        }), 201

    except sqlite3.IntegrityError:

        return jsonify({
            "erro": "Email já cadastrado"
        }), 409

    finally:
        conn.close()

# ─────────────────────────────────────────────
# API — DASHBOARD
# ─────────────────────────────────────────────
@app.route("/api/dashboard")
@login_requerido
def dashboard():
    conn = get_db()
    total     = conn.execute("SELECT COUNT(*) FROM patinetes").fetchone()[0]
    disponiveis = conn.execute("SELECT COUNT(*) FROM patinetes WHERE status='disponivel'").fetchone()[0]
    manutencao  = conn.execute("SELECT COUNT(*) FROM patinetes WHERE status='manutencao'").fetchone()[0]
    alerta      = conn.execute("SELECT COUNT(*) FROM patinetes WHERE bateria < 20").fetchone()[0]
    km_total    = conn.execute("SELECT SUM(quilometragem) FROM patinetes").fetchone()[0] or 0
    ultimas     = conn.execute("""
        SELECT m.data, m.tipo, m.descricao, p.numero_registro
        FROM manutencoes m JOIN patinetes p ON p.id = m.patinete_id
        ORDER BY m.id DESC LIMIT 5
    """).fetchall()
    conn.close()
    return jsonify({
        "total": total,
        "disponiveis": disponiveis,
        "manutencao": manutencao,
        "alerta_bateria": alerta,
        "km_total": round(km_total, 1),
        "ultimas_manutencoes": [dict(r) for r in ultimas]
    })

# ─────────────────────────────────────────────
# API — PATINETES
# ─────────────────────────────────────────────
@app.route("/api/patinetes", methods=["GET"])
@login_requerido
def listar_patinetes():
    conn = get_db()
    rows = conn.execute("SELECT * FROM patinetes ORDER BY numero_registro").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/patinetes", methods=["POST"])
@login_requerido
def cadastrar_patinete():
    d = request.get_json()
    conn = get_db()
    try:
        conn.execute("""INSERT INTO patinetes
            (numero_registro, lat, lng, bateria, quilometragem, status)
            VALUES (?,?,?,?,?,?)""",
            (d["numero_registro"],
             d.get("lat", -23.5558),
             d.get("lng", -46.6396),
             d.get("bateria", 100),
             d.get("quilometragem", 0),
             d.get("status", "disponivel")))
        conn.commit()
        return jsonify({"ok": True, "mensagem": "Patinete cadastrado!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"erro": "Número de registro já existe"}), 409
    finally:
        conn.close()

@app.route("/api/patinetes/<int:pid>", methods=["PUT"])
@login_requerido
def atualizar_patinete(pid):
    d = request.get_json()
    conn = get_db()
    conn.execute("""UPDATE patinetes SET
        lat=?, lng=?, bateria=?, quilometragem=?, status=?
        WHERE id=?""",
        (d["lat"], d["lng"], d["bateria"], d["quilometragem"], d["status"], pid))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/patinetes/<int:pid>", methods=["DELETE"])
@login_requerido
def deletar_patinete(pid):
    conn = get_db()
    conn.execute("DELETE FROM patinetes WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

# ─────────────────────────────────────────────
# API — MANUTENÇÕES
# ─────────────────────────────────────────────
@app.route("/api/manutencoes", methods=["GET"])
@login_requerido
def listar_manutencoes():
    pid = request.args.get("patinete_id")
    conn = get_db()
    if pid:
        rows = conn.execute("""
            SELECT m.*, p.numero_registro FROM manutencoes m
            JOIN patinetes p ON p.id = m.patinete_id
            WHERE m.patinete_id=? ORDER BY m.id DESC""", (pid,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT m.*, p.numero_registro FROM manutencoes m
            JOIN patinetes p ON p.id = m.patinete_id
            ORDER BY m.id DESC""").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/manutencoes", methods=["POST"])
@login_requerido
def registrar_manutencao():
    d = request.get_json()
    conn = get_db()
    conn.execute("""INSERT INTO manutencoes
        (patinete_id, tipo, descricao, custo, data, tecnico)
        VALUES (?,?,?,?,?,?)""",
        (d["patinete_id"], d["tipo"], d.get("descricao",""),
         d.get("custo", 0), d["data"], d.get("tecnico","")))
    conn.execute("UPDATE patinetes SET ultima_manutencao=? WHERE id=?",
                 (d["data"], d["patinete_id"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "mensagem": "Manutenção registrada!"}), 201

@app.route("/api/manutencoes/<int:mid>", methods=["DELETE"])
@login_requerido
def deletar_manutencao(mid):
    conn = get_db()
    conn.execute("DELETE FROM manutencoes WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

# ─────────────────────────────────────────────
# INICIAR
# ─────────────────────────────────────────────
criar_banco()

if __name__ == "__main__":
    app.run(debug=True)