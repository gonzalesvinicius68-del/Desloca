from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import hashlib
import os

app = Flask(__name__)
app.secret_key = "desloca_gestao_2024"
CORS(app)

DATABASE_URL = os.getenv("DATABASE_URL")


def get_db():
    return psycopg2.connect(DATABASE_URL)


def criar_banco():
    conn = get_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS patinetes (
            id SERIAL PRIMARY KEY,
            numero_registro TEXT UNIQUE NOT NULL,
            lat REAL DEFAULT -23.5558,
            lng REAL DEFAULT -46.6396,
            bateria INTEGER DEFAULT 100,
            quilometragem REAL DEFAULT 0,
            status TEXT DEFAULT 'disponivel',
            ultima_manutencao TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS manutencoes (
            id SERIAL PRIMARY KEY,
            patinete_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            descricao TEXT,
            custo REAL DEFAULT 0,
            data TEXT NOT NULL,
            tecnico TEXT,
            FOREIGN KEY (patinete_id) REFERENCES patinetes(id)
        )
    """)

    senha_padrao = hashlib.sha256("admin123".encode()).hexdigest()

    try:
        c.execute(
            "INSERT INTO usuarios (nome, email, senha) VALUES (%s, %s, %s)",
            ("Administrador", "admin@desloca.com", senha_padrao)
        )
    except psycopg2.IntegrityError:
        conn.rollback()

    c.execute("SELECT COUNT(*) AS total FROM patinetes")
    total_patinetes = c.fetchone()["total"]

    if total_patinetes == 0:
        exemplos = [
            ("PAT-0001", -23.5505, -46.6333, 92, 145.3, "disponivel", "2024-03-10"),
            ("PAT-0002", -23.5620, -46.6550, 78, 230.1, "disponivel", "2024-02-28"),
            ("PAT-0003", -23.5490, -46.6420, 23, 412.7, "manutencao", "2024-01-15"),
            ("PAT-0004", -23.5710, -46.6300, 55, 89.0, "disponivel", "2024-03-05"),
            ("PAT-0005", -23.5580, -46.6600, 8, 567.4, "alerta", "2023-12-20"),
        ]

        c.executemany("""
            INSERT INTO patinetes
            (numero_registro, lat, lng, bateria, quilometragem, status, ultima_manutencao)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, exemplos)

    conn.commit()
    c.close()
    conn.close()


def login_requerido(f):
    from functools import wraps

    @wraps(f)
    def decorador(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)

    return decorador


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


@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json()
    senha_hash = hashlib.sha256(d["senha"].encode()).hexdigest()

    conn = get_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    c.execute(
        "SELECT * FROM usuarios WHERE email=%s AND senha=%s",
        (d["email"], senha_hash)
    )

    u = c.fetchone()

    c.close()
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


@app.route("/api/cadastro", methods=["POST"])
def cadastro():
    d = request.get_json()

    nome = d.get("nome")
    email = d.get("email")
    senha = d.get("senha")

    if not nome or not email or not senha:
        return jsonify({"erro": "Preencha todos os campos"}), 400

    senha_hash = hashlib.sha256(senha.encode()).hexdigest()

    conn = get_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        c.execute(
            "INSERT INTO usuarios (nome, email, senha) VALUES (%s, %s, %s)",
            (nome, email, senha_hash)
        )
        conn.commit()
        return jsonify({"ok": True, "mensagem": "Usuário criado com sucesso"}), 201

    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({"erro": "Email já cadastrado"}), 409

    finally:
        c.close()
        conn.close()


@app.route("/api/dashboard")
@login_requerido
def dashboard():
    conn = get_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    c.execute("SELECT COUNT(*) AS total FROM patinetes")
    total = c.fetchone()["total"]

    c.execute("SELECT COUNT(*) AS total FROM patinetes WHERE status='disponivel'")
    disponiveis = c.fetchone()["total"]

    c.execute("SELECT COUNT(*) AS total FROM patinetes WHERE status='manutencao'")
    manutencao = c.fetchone()["total"]

    c.execute("SELECT COUNT(*) AS total FROM patinetes WHERE bateria < 20")
    alerta = c.fetchone()["total"]

    c.execute("SELECT SUM(quilometragem) AS total FROM patinetes")
    km_total = c.fetchone()["total"] or 0

    c.execute("""
        SELECT m.data, m.tipo, m.descricao, p.numero_registro
        FROM manutencoes m
        JOIN patinetes p ON p.id = m.patinete_id
        ORDER BY m.id DESC
        LIMIT 5
    """)
    ultimas = c.fetchall()

    c.close()
    conn.close()

    return jsonify({
        "total": total,
        "disponiveis": disponiveis,
        "manutencao": manutencao,
        "alerta_bateria": alerta,
        "km_total": round(km_total, 1),
        "ultimas_manutencoes": ultimas
    })


@app.route("/api/patinetes", methods=["GET"])
@login_requerido
def listar_patinetes():
    conn = get_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    c.execute("SELECT * FROM patinetes ORDER BY numero_registro")
    rows = c.fetchall()

    c.close()
    conn.close()

    return jsonify(rows)


@app.route("/api/patinetes", methods=["POST"])
@login_requerido
def cadastrar_patinete():
    d = request.get_json()

    conn = get_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        c.execute("""
            INSERT INTO patinetes
            (numero_registro, lat, lng, bateria, quilometragem, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            d["numero_registro"],
            d.get("lat", -23.5558),
            d.get("lng", -46.6396),
            d.get("bateria", 100),
            d.get("quilometragem", 0),
            d.get("status", "disponivel")
        ))

        conn.commit()
        return jsonify({"ok": True, "mensagem": "Patinete cadastrado!"}), 201

    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({"erro": "Número de registro já existe"}), 409

    finally:
        c.close()
        conn.close()


@app.route("/api/patinetes/<int:pid>", methods=["PUT"])
@login_requerido
def atualizar_patinete(pid):
    d = request.get_json()

    conn = get_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    c.execute("""
        UPDATE patinetes SET
        lat=%s, lng=%s, bateria=%s, quilometragem=%s, status=%s
        WHERE id=%s
    """, (
        d["lat"],
        d["lng"],
        d["bateria"],
        d["quilometragem"],
        d["status"],
        pid
    ))

    conn.commit()
    c.close()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/patinetes/<int:pid>", methods=["DELETE"])
@login_requerido
def deletar_patinete(pid):
    conn = get_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    c.execute("DELETE FROM patinetes WHERE id=%s", (pid,))

    conn.commit()
    c.close()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/manutencoes", methods=["GET"])
@login_requerido
def listar_manutencoes():
    pid = request.args.get("patinete_id")

    conn = get_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if pid:
        c.execute("""
            SELECT m.*, p.numero_registro
            FROM manutencoes m
            JOIN patinetes p ON p.id = m.patinete_id
            WHERE m.patinete_id=%s
            ORDER BY m.id DESC
        """, (pid,))
    else:
        c.execute("""
            SELECT m.*, p.numero_registro
            FROM manutencoes m
            JOIN patinetes p ON p.id = m.patinete_id
            ORDER BY m.id DESC
        """)

    rows = c.fetchall()

    c.close()
    conn.close()

    return jsonify(rows)


@app.route("/api/manutencoes", methods=["POST"])
@login_requerido
def registrar_manutencao():
    d = request.get_json()

    conn = get_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    c.execute("""
        INSERT INTO manutencoes
        (patinete_id, tipo, descricao, custo, data, tecnico)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        d["patinete_id"],
        d["tipo"],
        d.get("descricao", ""),
        d.get("custo", 0),
        d["data"],
        d.get("tecnico", "")
    ))

    c.execute(
        "UPDATE patinetes SET ultima_manutencao=%s WHERE id=%s",
        (d["data"], d["patinete_id"])
    )

    conn.commit()
    c.close()
    conn.close()

    return jsonify({"ok": True, "mensagem": "Manutenção registrada!"}), 201


@app.route("/api/manutencoes/<int:mid>", methods=["DELETE"])
@login_requerido
def deletar_manutencao(mid):
    conn = get_db()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    c.execute("DELETE FROM manutencoes WHERE id=%s", (mid,))

    conn.commit()
    c.close()
    conn.close()

    return jsonify({"ok": True})


criar_banco()

if __name__ == "__main__":
    app.run(debug=True)