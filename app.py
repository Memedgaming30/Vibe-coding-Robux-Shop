import os
import json
import secrets
import hashlib
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, g,
)
import config
from db import get_db, init_db
from gateway import create_address, consolidate
from webhook_verify import verify_webhook
from discord_notify import send_discord

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# ── Ensure DB + admin exist on every request ─────────────────────────

@app.before_request
def ensure_db():
    init_db()
    bootstrap_admin()

# ── Database helpers ─────────────────────────────────────────────────

def db():
    if "db" not in g:
        g.db = get_db()
    return g.db


@app.teardown_appcontext
def close_db(exc):
    conn = g.pop("db", None)
    if conn:
        conn.close()


# ── Auth helpers ─────────────────────────────────────────────────────

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def login_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapped


def admin_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        user = current_user()
        if not user or not user["is_admin"]:
            flash("Admin access required.", "error")
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapped


# ── Template context ─────────────────────────────────────────────────

@app.context_processor
def inject_user():
    return {"user": current_user()}


# ── Bootstrap admin on first run ─────────────────────────────────────

def bootstrap_admin():
    conn = get_db()
    exists = conn.execute(
        "SELECT id FROM users WHERE email=?", (config.ADMIN_EMAIL,)
    ).fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO users (email, password_hash, game_username, robux, is_admin) "
            "VALUES (?, ?, ?, 0, 1)",
            (config.ADMIN_EMAIL, hash_pw(config.ADMIN_PASSWORD), "admin"),
        )
        conn.commit()
        print(f"[boot] admin account created: {config.ADMIN_EMAIL}")
    conn.close()


# ═══════════════════════════════════════════════════════════════════
#  PUBLIC ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    user = current_user()
    if user and not user["game_username"]:
        return redirect(url_for("setup_username"))
    packages = [
        {"robux": 100, "usdt": 1, "label": "Starter"},
        {"robux": 500, "usdt": 5, "label": "Popular"},
        {"robux": 1000, "usdt": 10, "label": "Pro"},
        {"robux": 2500, "usdt": 25, "label": "Mega"},
    ]
    return render_template("index.html", packages=packages)


# ── Auth ─────────────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        suggested = f"player_{secrets.token_hex(3)}@robuxshop.gg"
        return render_template("register.html", suggested_email=suggested)

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    if not email or len(password) < 6:
        flash("Email required and password must be 6+ chars.", "error")
        return redirect(url_for("register"))

    conn = db()
    exists = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if exists:
        flash("Email already registered.", "error")
        return redirect(url_for("register"))

    conn.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
        (email, hash_pw(password)),
    )
    conn.commit()
    user = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    session["user_id"] = user["id"]
    return redirect(url_for("setup_username"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    user = db().execute(
        "SELECT * FROM users WHERE email=? AND password_hash=?",
        (email, hash_pw(password)),
    ).fetchone()
    if not user:
        flash("Invalid credentials.", "error")
        return redirect(url_for("login"))
    session["user_id"] = user["id"]
    if user["is_admin"]:
        return redirect(url_for("admin_dashboard"))
    if not user["game_username"]:
        return redirect(url_for("setup_username"))
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/setup-username", methods=["GET", "POST"])
@login_required
def setup_username():
    user = current_user()
    if user["game_username"] and user["game_username"] != "admin":
        return redirect(url_for("account"))

    if request.method == "GET":
        return render_template("setup_username.html")

    username = request.form.get("username", "").strip().lower()
    username = username.lstrip("@")
    if not username or len(username) < 3:
        flash("Username must be at least 3 characters.", "error")
        return redirect(url_for("setup_username"))
    if not username.isalnum() and "_" not in username:
        flash("Letters, numbers, underscores only.", "error")
        return redirect(url_for("setup_username"))

    conn = db()
    taken = conn.execute(
        "SELECT id FROM users WHERE game_username=?", (username,)
    ).fetchone()
    if taken:
        flash("Username taken.", "error")
        return redirect(url_for("setup_username"))

    conn.execute(
        "UPDATE users SET game_username=? WHERE id=?", (username, user["id"])
    )
    conn.commit()
    flash(f"Welcome, @{username}!", "success")
    return redirect(url_for("account"))


# ── Account ──────────────────────────────────────────────────────────

@app.route("/account")
@login_required
def account():
    user = current_user()
    if not user["game_username"]:
        return redirect(url_for("setup_username"))
    txns = db().execute(
        "SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (user["id"],),
    ).fetchall()
    return render_template("account.html", txns=txns)


# ── Buy flow ─────────────────────────────────────────────────────────

@app.route("/buy/<int:robux_amount>")
@login_required
def buy(robux_amount):
    user = current_user()
    if not user["game_username"]:
        return redirect(url_for("setup_username"))

    valid = {100: 1, 500: 5, 1000: 10, 2500: 25}
    usdt = valid.get(robux_amount)
    if not usdt:
        flash("Invalid package.", "error")
        return redirect(url_for("index"))

    stock = db().execute("SELECT robux FROM admin_stock WHERE id=1").fetchone()
    if not stock or stock["robux"] < robux_amount:
        flash("Out of stock. Try a smaller package.", "error")
        return redirect(url_for("index"))

    return render_template(
        "checkout.html",
        robux_amount=robux_amount,
        usdt_amount=usdt,
        chain_id=config.CHAIN_ID,
        token_address=config.USDT_TOKEN_ADDRESS,
        blockchain_name=config.BLOCKCHAIN_NAME,
    )


# ── API: create deposit address ──────────────────────────────────────

@app.route("/api/create-deposit", methods=["POST"])
@login_required
def api_create_deposit():
    user = current_user()
    data = request.get_json() or {}
    robux_amount = data.get("robux_amount", 0)
    usdt_amount = data.get("usdt_amount", 0)

    reference = f"usr{user['id']}-{secrets.token_hex(4)}"

    status_code, body = create_address(
        vm_type="EVM",
        name=f"Robux purchase by @{user['game_username']}",
        reference=reference,
    )

    if status_code >= 400:
        return jsonify({"error": body}), status_code

    conn = db()
    conn.execute(
        "INSERT INTO addresses (address, reference, vm_type, gateway_id, user_id, robux_amount, usdt_amount) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (body["address"], reference, body["vmType"], body["id"],
         user["id"], robux_amount, str(usdt_amount)),
    )
    conn.execute(
        "INSERT INTO transactions (reference, user_id, usdt_amount, robux_amount, address, status) "
        "VALUES (?, ?, ?, ?, ?, 'PENDING')",
        (f"{reference}-consolidate", user["id"], str(usdt_amount),
         robux_amount, body["address"]),
    )
    conn.commit()

    return jsonify({
        "address": body["address"],
        "reference": reference,
        "vmType": body["vmType"],
    })


# ── API: deposit notification (called by deposit-watch on frontend) ──

@app.route("/api/deposits/notify", methods=["POST"])
@login_required
def api_deposit_notify():
    data = request.get_json() or {}
    address = data.get("address")
    chain_id = data.get("chainId")
    amount = data.get("amount")
    token_address = data.get("tokenAddress")

    if not address or not chain_id or amount is None:
        return jsonify({"error": "address, chainId, amount required"}), 400

    addr_row = db().execute(
        "SELECT * FROM addresses WHERE address=?", (address,)
    ).fetchone()
    if not addr_row:
        return jsonify({"error": "unknown address"}), 404

    tx_reference = f"{addr_row['reference']}-consolidate"

    status_code, body = consolidate(
        address=address,
        amount=float(amount),
        blockchain_name=config.BLOCKCHAIN_NAME,
        transaction_reference=tx_reference,
        token_address=token_address,
    )

    if not (200 <= status_code < 300):
        err = body.get("error", "") if isinstance(body, dict) else ""
        if err in ("error.insufficientBalance", "error.consolidationIsProcessing"):
            return "", 202
        if err == "error.transactionAlreadyExist":
            return "", 200
        return jsonify(body), status_code

    conn = db()
    conn.execute(
        "UPDATE transactions SET status='PROCESSING' WHERE reference=? AND status='PENDING'",
        (tx_reference,),
    )
    conn.commit()
    return jsonify({"status": "consolidating", "reference": tx_reference})


# ── API: check transaction status (polled by frontend) ───────────────

@app.route("/api/tx-status/<reference>")
@login_required
def api_tx_status(reference):
    row = db().execute(
        "SELECT status, robux_amount, net_amount, tx_hash, confirmed_at "
        "FROM transactions WHERE reference=?",
        (reference,),
    ).fetchone()
    if not row:
        return jsonify({"status": "unknown"})
    return jsonify(dict(row))


# ═══════════════════════════════════════════════════════════════════
#  WEBHOOK — the ONLY place that credits the ledger
# ═══════════════════════════════════════════════════════════════════

@app.route("/webhooks/gateway", methods=["POST"])
def webhook_handler():
    raw_body = request.get_data()
    signature = request.headers.get("x-akpay-webhook-signature", "")

    if not verify_webhook(raw_body, signature, config.WEBHOOK_SECRET):
        print("[webhook] signature verification FAILED")
        return "", 401

    event = json.loads(raw_body)
    ref = event.get("reference", "")

    conn = get_db()

    if event.get("status") == "confirmed":
        tx = conn.execute(
            "SELECT * FROM transactions WHERE reference=? AND status != 'CONFIRMED'",
            (ref,),
        ).fetchone()

        if tx:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "UPDATE transactions SET status='CONFIRMED', net_amount=?, "
                    "tx_hash=?, blockchain=?, confirmed_at=CURRENT_TIMESTAMP "
                    "WHERE reference=? AND status != 'CONFIRMED'",
                    (event.get("netAmount"), event.get("txHash"),
                     event.get("blockchain"), ref),
                )
                conn.execute(
                    "UPDATE users SET robux = robux + ? WHERE id=?",
                    (tx["robux_amount"], tx["user_id"]),
                )
                conn.execute(
                    "UPDATE admin_stock SET robux = MAX(0, robux - ?) WHERE id=1",
                    (tx["robux_amount"],),
                )
                conn.execute("COMMIT")

                user = conn.execute(
                    "SELECT * FROM users WHERE id=?", (tx["user_id"],)
                ).fetchone()

                print(
                    f"[settle] +{tx['robux_amount']} robux to @{user['game_username']} "
                    f"(ref={ref}, tx={event.get('txHash')})"
                )

                send_discord(
                    title="💎 Robux Purchase Confirmed",
                    description=f"@{user['game_username']} bought {tx['robux_amount']} Robux",
                    color=0x00FF88,
                    fields=[
                        {"name": "USDT Paid", "value": tx["usdt_amount"]},
                        {"name": "Net Amount", "value": event.get("netAmount", "?")},
                        {"name": "Robux", "value": str(tx["robux_amount"])},
                        {"name": "Tx Hash", "value": event.get("txHash", "?")[:16] + "..."},
                        {"name": "Blockchain", "value": event.get("blockchain", "?")},
                        {"name": "Reference", "value": ref},
                    ],
                )
            except Exception:
                conn.execute("ROLLBACK")
                raise
        else:
            print(f"[webhook] duplicate or unknown ref={ref} — no-op")

    elif event.get("status") == "failed":
        conn.execute(
            "UPDATE transactions SET status='FAILED', error_message=? WHERE reference=?",
            (event.get("errorMessage", "unknown"), ref),
        )
        conn.commit()
        send_discord(
            title="❌ Transaction Failed",
            description=f"ref={ref}",
            color=0xFF0000,
            fields=[
                {"name": "Error", "value": event.get("errorMessage", "unknown")},
            ],
        )

    conn.close()
    return "", 200


# ═══════════════════════════════════════════════════════════════════
#  ADMIN ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = db()
    stock = conn.execute("SELECT robux FROM admin_stock WHERE id=1").fetchone()
    user_count = conn.execute("SELECT COUNT(*) as c FROM users WHERE is_admin=0").fetchone()
    tx_count = conn.execute("SELECT COUNT(*) as c FROM transactions").fetchone()
    confirmed = conn.execute(
        "SELECT COUNT(*) as c FROM transactions WHERE status='CONFIRMED'"
    ).fetchone()
    recent_txns = conn.execute(
        "SELECT t.*, u.game_username FROM transactions t "
        "JOIN users u ON t.user_id = u.id "
        "ORDER BY t.created_at DESC LIMIT 20"
    ).fetchall()
    users = conn.execute(
        "SELECT * FROM users WHERE is_admin=0 ORDER BY created_at DESC"
    ).fetchall()
    return render_template(
        "admin/dashboard.html",
        stock=stock,
        user_count=user_count["c"],
        tx_count=tx_count["c"],
        confirmed_count=confirmed["c"],
        recent_txns=recent_txns,
        users=users,
    )


@app.route("/admin/stock", methods=["POST"])
@admin_required
def admin_update_stock():
    new_stock = request.form.get("robux", type=int)
    if new_stock is not None and new_stock >= 0:
        conn = db()
        conn.execute("UPDATE admin_stock SET robux=? WHERE id=1", (new_stock,))
        conn.commit()
        flash(f"Stock updated to {new_stock} Robux.", "success")
    return redirect(url_for("admin_dashboard"))


# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()
    bootstrap_admin()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
