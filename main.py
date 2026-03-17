"""
🧠 SENTINEL — MANAGER AGENT
Cerveau central du système.
- Analyse intelligente via Claude Haiku (décisions importantes)
- Groq comme fallback (gratuit)
- Coordonne Skills Hunter + Trading Agent
- Rapports matin/soir/hebdo/mensuel
- JAMAIS d'exécution sans approbation Samet ✅/❌
"""

import os, json, time, requests, schedule, threading
import yfinance as yf
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, request, jsonify
from groq import Groq
import anthropic

# Import config
import sys
sys.path.append(os.path.dirname(__file__))
try:
    from sentinel_config import *
except:
    pass

# Lecture directe — fallback si config non chargé
DISCORD_WEBHOOK    = os.getenv("DW_URL", os.getenv("DISCORD_WEBHOOK_URL", ""))
GROQ_API_KEY       = os.getenv("LA", os.getenv("GROQ_API_KEY", ""))
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_KEY", "")
DISCORD_TOKEN      = os.getenv("BT", os.getenv("DISCORD_TOKEN", ""))
DISCORD_CHANNEL_ID = os.getenv("BC", os.getenv("DISCORD_CHANNEL_ID", ""))
AGENT_SECRET       = os.getenv("SS", os.getenv("SENTINEL_SECRET", "sentinel-secret-key"))
GMAIL_ADDRESS      = os.getenv("MF", os.getenv("GMAIL_ADDRESS", ""))
GMAIL_APP_PWD      = os.getenv("MP", os.getenv("GMAIL_APP_PASSWORD", ""))
MANAGER_URL        = os.getenv("MANAGER_URL", "http://localhost:5001")
SKILLS_URL         = os.getenv("SKILLS_URL", "http://localhost:5002")
TRADING_URL        = os.getenv("TRADING_URL", "http://localhost:5003")

# ─── INIT ─────────────────────────────────────────────────
app          = Flask(__name__)
groq_client  = Groq(api_key=GROQ_API_KEY)
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_API_KEY else None
STATE        = Path("manager_state.json")

SYSTEM_PROMPT = (
    "Tu es le Manager Agent de SENTINEL, un système d'investissement éthique. "
    "Tu analyses les données de marché et proposes des décisions d'investissement. "
    "Tes réponses sont concises, en français, max 3 phrases."
)

# ─── HELPERS ──────────────────────────────────────────────
def now_str():
    return datetime.now().strftime("%d/%m/%Y %H:%M")

def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {
        "pending": [], "approved": [], "rejected": [],
        "agents": {}, "events": [], "last_updated": ""
    }

def save_state(s: dict):
    s["last_updated"] = now_str()
    STATE.write_text(json.dumps(s, indent=2, ensure_ascii=False))

def log_event(msg: str):
    s = load_state()
    s["events"].append({"time": now_str(), "msg": msg})
    s["events"] = s["events"][-50:]
    save_state(s)

# ─── LLM — Claude Haiku (important) + Groq (rapide) ──────
def ask_claude(prompt: str, system: str = None) -> str:
    """Claude Haiku pour les décisions importantes"""
    if not claude_client:
        return ask_groq(prompt, system, fast=False)
    try:
        msg = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=system or SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"⚠️ Claude Haiku erreur : {e} → fallback Groq")
        return ask_groq(prompt, system, fast=False)

def ask_groq(prompt: str, system: str = None, fast: bool = False) -> str:
    """Groq pour les analyses rapides et fréquentes"""
    try:
        model = "llama-3.1-8b-instant" if fast else "llama-3.3-70b-versatile"
        response = groq_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system or SYSTEM_PROMPT},
                {"role": "user",   "content": prompt}
            ],
            max_tokens=300, temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Groq erreur : {e}")
        return "Analyse indisponible"

def analyze_market(prices: dict) -> str:
    """Analyse marché via Claude Haiku — décision importante"""
    summary = ", ".join(
        f"{s}: {d['price']}$ ({d['change']:+.1f}%)"
        for s, d in list(prices.items())[:6]
    )
    return ask_claude(
        f"Voici les prix actuels du portefeuille : {summary}. "
        f"Donne une analyse rapide du marché aujourd'hui et un conseil d'action."
    )

def analyze_dip(symbol: str, change: float, price: float) -> str:
    """Analyse un dip via Claude Haiku — décision financière importante"""
    return ask_claude(
        f"{symbol} a baissé de {change:.1f}% à {price}$. "
        f"Est-ce un bon point d'entrée pour un investissement éthique long terme ? "
        f"Donne une recommandation claire en 2 phrases."
    )

def analyze_skill(skill_title: str, skill_desc: str) -> str:
    """Analyse pertinence d'un skill via Groq — tâche répétitive"""
    return ask_groq(
        f"Un skill a été trouvé : '{skill_title}' - {skill_desc}. "
        f"Est-ce pertinent pour un bot de DCA mensuel sur ETFs éthiques ? "
        f"Réponds par OUI/NON et une raison courte.",
        fast=True
    )

# ─── DISCORD ──────────────────────────────────────────────
def send_discord(title: str, fields: list, color: int = 0xC9A84C, components: list = None):
    embed = {
        "title": title, "color": color, "fields": fields,
        "footer": {"text": f"🛡️ SENTINEL Manager • {now_str()}"},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    payload = {"embeds": [embed]}
    if components:
        payload["components"] = components
    try:
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        print(f"✅ Discord → {title}")
    except Exception as e:
        print(f"❌ Discord erreur : {e}")

def send_decision(title: str, desc: str, action_type: str, action_data: dict, color=0xF39C12):
    """Envoie proposition avec boutons ✅/❌ — JAMAIS exécutée sans Samet"""
    s = load_state()
    did = f"{action_type}_{int(time.time())}"
    s["pending"].append({
        "id": did, "title": title, "type": action_type,
        "data": action_data, "at": now_str(), "status": "pending"
    })
    save_state(s)

    components = [{"type": 1, "components": [
        {"type": 2, "style": 3, "label": "✅ Approuver", "custom_id": f"approve_{did}"},
        {"type": 2, "style": 4, "label": "❌ Refuser",   "custom_id": f"reject_{did}"}
    ]}]
    send_discord(f"🟡 DÉCISION — {title}", [
        {"name": "📋 Proposition", "value": desc,            "inline": False},
        {"name": "🔑 ID",          "value": f"`{did}`",       "inline": True},
        {"name": "⚠️ Action",      "value": "Clique ✅ ou ❌", "inline": True},
    ], color=color, components=components)
    log_event(f"Décision envoyée : {title}")
    return did

# ─── DONNÉES MARCHÉ ───────────────────────────────────────
def get_prices() -> dict:
    prices = {}
    for symbol in PORTFOLIO:
        try:
            info = yf.Ticker(symbol).fast_info
            prices[symbol] = {
                "price":  round(info.get("lastPrice", 0), 2),
                "change": round(info.get("regularMarketChangePercent", 0), 2),
            }
        except:
            prices[symbol] = {"price": 0, "change": 0}
    return prices

def get_mood() -> str:
    try:
        c = yf.Ticker("SPY").fast_info.get("regularMarketChangePercent", 0)
        if c > 1:    return "🟢 Haussier"
        elif c > 0:  return "🟡 Stable"
        elif c > -1: return "🟠 Prudent"
        else:        return "🔴 Baissier"
    except:
        return "❓ Indisponible"

# ─── COMMUNICATION INTER-AGENTS ───────────────────────────
def ping_agent(url: str, name: str) -> bool:
    """Vérifie si un agent répond"""
    try:
        r = requests.get(f"{url}/health", timeout=5,
                         headers={"X-Secret": AGENT_SECRET})
        return r.status_code == 200
    except:
        return False

def send_to_skills(task: str, topic: str):
    """Envoie une tâche au Skills Hunter"""
    try:
        requests.post(f"{SKILLS_URL}/task",
                      json={"task": task, "topic": topic},
                      headers={"X-Secret": AGENT_SECRET}, timeout=10)
        log_event(f"Tâche → Skills Hunter : {task}")
        print(f"📡 Skills Hunter → {task}")
    except Exception as e:
        print(f"❌ Skills Hunter injoignable : {e}")

def send_to_trading(task: str, data: dict = None):
    """Envoie une instruction au Trading Agent"""
    try:
        requests.post(f"{TRADING_URL}/task",
                      json={"task": task, "data": data or {}},
                      headers={"X-Secret": AGENT_SECRET}, timeout=10)
        log_event(f"Tâche → Trading Agent : {task}")
        print(f"📡 Trading Agent → {task}")
    except Exception as e:
        print(f"❌ Trading Agent injoignable : {e}")

# ─── VÉRIFICATIONS AUTOMATIQUES ───────────────────────────
def check_dips():
    print("📉 Vérification dips...")
    prices = get_prices()
    s = load_state()
    today = datetime.now().strftime("%Y-%m-%d")

    for symbol, data in prices.items():
        if data["change"] / 100 <= DIP_THRESHOLD and data["price"] > 0:
            already = any(
                d["data"].get("symbol") == symbol and d["at"].startswith(today[:10])
                for d in s["pending"]
            )
            if already:
                continue

            # Analyse Groq du dip
            analysis = analyze_dip(symbol, data["change"], data["price"])
            extra = round(DCA_AMOUNT * 0.5, 2)

            send_decision(
                f"Dip {symbol} ({data['change']:+.1f}%)",
                f"**{symbol}** baisse de **{data['change']:+.1f}%** → {data['price']}$\n\n"
                f"🧠 **Analyse IA** : {analysis}\n\n"
                f"💡 Renforcer de **{extra}€** ?",
                action_type="buy_dip",
                action_data={"symbol": symbol, "amount": extra, "price": data["price"]},
                color=0xF39C12
            )

def check_systems():
    """Vérifie Railway + les 2 agents"""
    print("🔍 Vérification systèmes...")
    s = load_state()

    skills_ok  = ping_agent(SKILLS_URL,  "Skills Hunter")
    trading_ok = ping_agent(TRADING_URL, "Trading Agent")

    s["agents"]["skills_hunter"]  = "✅ Online" if skills_ok  else "❌ Offline"
    s["agents"]["trading_agent"]  = "✅ Online" if trading_ok else "❌ Offline"
    s["agents"]["manager"]        = "✅ Online"
    s["agents"]["last_check"]     = now_str()
    save_state(s)

    if not skills_ok or not trading_ok:
        send_discord("⚠️ Agent hors ligne détecté", [
            {"name": "🔍 Skills Hunter",  "value": "✅" if skills_ok  else "❌ Offline", "inline": True},
            {"name": "📈 Trading Agent",  "value": "✅" if trading_ok else "❌ Offline", "inline": True},
        ], color=0xE74C3C)

def auto_coordinate():
    """Coordination intelligente quotidienne"""
    print("🎯 Coordination automatique...")
    prices = get_prices()
    mood   = get_mood()

    # Marché baissier → Trading Agent en mode prudent
    if "Baissier" in mood:
        send_to_trading("mode_prudent", {"reason": "Marché baissier détecté"})

    # Forte baisse sur un actif → demander analyse Trading
    for symbol, data in prices.items():
        if data["change"] <= -5:
            send_to_trading("analyze_signal", {
                "symbol": symbol, "change": data["change"]
            })
            break

    # Lundi → Skills Hunter cherche nouvelles ressources
    if datetime.now().weekday() == 0:
        send_to_skills("weekly_search", "DCA ETF strategy 2026")

# ─── RAPPORTS ─────────────────────────────────────────────
def morning_report():
    print("☀️ Rapport matinal...")
    prices  = get_prices()
    mood    = get_mood()
    s       = load_state()
    analysis = analyze_market(prices)

    gainers = sorted([(k,v) for k,v in prices.items() if v["change"]>0], key=lambda x: -x[1]["change"])
    losers  = sorted([(k,v) for k,v in prices.items() if v["change"]<0], key=lambda x: x[1]["change"])

    send_discord("☀️ Rapport Matinal — SENTINEL", [
        {"name": "🌍 Marché",    "value": mood, "inline": True},
        {"name": "📅 Date",      "value": datetime.now().strftime("%d/%m/%Y"), "inline": True},
        {"name": "📈 Hausse",
         "value": "\n".join(f"**{s}** {d['price']}$ ({d['change']:+.1f}%)" for s,d in gainers[:3]) or "Aucun",
         "inline": True},
        {"name": "📉 Baisse",
         "value": "\n".join(f"**{s}** {d['price']}$ ({d['change']:+.1f}%)" for s,d in losers[:3]) or "Aucun",
         "inline": True},
        {"name": "🧠 Analyse IA", "value": analysis, "inline": False},
        {"name": "⏳ En attente", "value": f"**{len(s['pending'])}** décision(s)", "inline": True},
        {"name": "📅 Prochain DCA", "value": _next_dca(), "inline": True},
    ], color=0xF39C12)
    auto_coordinate()

def evening_report():
    print("🌙 Rapport du soir...")
    prices = get_prices()
    s      = load_state()
    avg    = sum(d["change"] for d in prices.values()) / max(len(prices), 1)
    summary = ask_groq(
        f"Performance moyenne du portefeuille aujourd'hui : {avg:+.2f}%. "
        f"Fais un bilan du soir en 2 phrases, positif et motivant.",
        fast=True
    )

    send_discord("🌙 Rapport du Soir — SENTINEL", [
        {"name": f"{'📈' if avg>0 else '📉'} Performance", "value": f"**{avg:+.2f}%** moyenne", "inline": True},
        {"name": "🤖 Agents", "value": "\n".join(
            f"{k}: {v}" for k,v in s["agents"].items() if "last" not in k
        ) or "Vérification en cours...", "inline": True},
        {"name": "📊 Actifs", "value": "\n".join(
            f"{'🟢' if d['change']>0 else '🔴'} **{sym}** {d['price']}$ ({d['change']:+.1f}%)"
            for sym,d in prices.items()
        ), "inline": False},
        {"name": "🧠 Bilan IA", "value": summary, "inline": False},
    ], color=0x8B5CF6)

def weekly_report():
    print("📋 Rapport hebdo...")
    prices = get_prices()
    s      = load_state()
    top3   = sorted(prices.items(), key=lambda x: -x[1]["change"])[:3]
    top3_str = ", ".join(f"{sym}({d['change']:+.1f}%)" for sym,d in top3)
    analysis = ask_groq(
        f"Top performers cette semaine : {top3_str}. "
        f"Donne une synthèse hebdomadaire et une orientation pour la semaine prochaine."
    )

    send_discord("📋 Rapport Hebdomadaire — SENTINEL", [
        {"name": "🌍 Marché",    "value": get_mood(), "inline": True},
        {"name": "✅ Approuvées","value": str(len(s["approved"])),  "inline": True},
        {"name": "❌ Refusées",  "value": str(len(s["rejected"])),  "inline": True},
        {"name": "🏆 Top 3",
         "value": "\n".join(f"{'🥇🥈🥉'[i]} **{sym}** {d['change']:+.1f}%" for i,(sym,d) in enumerate(top3)),
         "inline": False},
        {"name": "🧠 Analyse IA", "value": analysis, "inline": False},
    ], color=0x2ECC71)

def samet_weekly_tasks():
    """
    Planning hebdomadaire de Samet — chaque lundi 08:30
    Tâches fixes + tâches SENTINEL en cours + documents à créer
    """
    print("📅 Planning hebdo Samet...")

    fixed_tasks = [
        "📁 Uploader WEEKLY-SUMMARY.md (Skills Hunter) dans le projet Claude",
        "✅ Vérifier les décisions en attente sur Discord (✅/❌)",
        "📊 Consulter le rapport matinal SENTINEL",
        "🔍 Regarder les skills proposés par Skills Hunter",
        "💰 Vérifier le cash disponible sur IB",
        "📧 Lire l'email hebdomadaire du Skills Hunter",
    ]

    sentinel_tasks = [
        "🚀 Créer compte Groq → groq.com → clé GROQ_API_KEY",
        "📤 Uploader les 6 fichiers SENTINEL sur GitHub (sameulas43)",
        "🚂 Déployer sentinel_skills.py sur Railway (nouveau service)",
        "🚂 Déployer sentinel_trading.py sur Railway (nouveau service)",
        "🚂 Mettre à jour sentinel_manager.py sur Railway",
        "⚙️ Configurer toutes les variables Railway (voir README.md)",
        "📧 Configurer Gmail App Password → GMAIL_APP_PASSWORD Railway",
        "🧪 Tester communication inter-agents via Discord",
        "📡 Vérifier que les 3 agents se voient bien via /health",
    ]

    doc_tasks = [
        "📄 agent-manager.md — rôle et tâches du Manager",
        "📄 agent-trading.md — signaux et exécution IBBot",
        "📄 skill-hunter.md — chasse GitHub/Reddit",
        "📄 security-engine.md — scan antivirus skills",
        "📄 ibbot-integration.md — fusion IBBot + écosystème",
    ]

    advice = ask_groq(
        "Donne un conseil motivant court pour quelqu'un qui construit un système "
        "d'investissement automatisé éthique semaine après semaine. 2 phrases max.",
        fast=True
    )

    send_discord("📅 Ton Planning de la Semaine — SENTINEL", [
        {"name": "📋 Tâches hebdomadaires fixes",
         "value": "\n".join(f"• {t}" for t in fixed_tasks),
         "inline": False},
        {"name": "─────────────────", "value": " ", "inline": False},
        {"name": "🚀 Priorités SENTINEL cette semaine",
         "value": "\n".join(f"• {t}" for t in sentinel_tasks[:6]),
         "inline": False},
        {"name": "📄 5 documents à créer avec Claude",
         "value": "\n".join(f"• {t}" for t in doc_tasks),
         "inline": False},
        {"name": "─────────────────", "value": " ", "inline": False},
        {"name": "🧠 Conseil IA", "value": advice, "inline": False},
        {"name": "💡 Rappel important",
         "value": "Observe les agents toute la semaine → note ce qui manque → vendredi on améliore 💪",
         "inline": False},
    ], color=0xC9A84C)

# ─── HELPERS ──────────────────────────────────────────────
def _next_dca() -> str:
    n = datetime.now()
    if n.day == 1: return "**Aujourd'hui !** 🚀"
    try:
        import calendar
        last = calendar.monthrange(n.year, n.month)[1]
        if n.month == 12:
            nxt = n.replace(year=n.year+1, month=1, day=1)
        else:
            nxt = n.replace(month=n.month+1, day=1)
        return f"Dans **{(nxt-n).days} jours**"
    except:
        return "Le 1er du mois"

# ─── API FLASK — COMMUNICATION INTER-AGENTS ───────────────
def check_secret():
    return request.headers.get("X-Secret") == AGENT_SECRET

@app.route("/health")
def health():
    return jsonify({"status": "online", "agent": "manager", "time": now_str()})

@app.route("/report", methods=["POST"])
def receive_report():
    """Reçoit un rapport d'un agent"""
    if not check_secret():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    agent   = data.get("agent", "unknown")
    message = data.get("message", "")
    details = data.get("details", {})

    print(f"📨 Rapport reçu de {agent} : {message}")
    log_event(f"{agent}: {message}")

    # Analyse Groq si pertinent
    if details:
        analysis = ask_groq(
            f"L'agent {agent} rapporte : {message}. Détails : {json.dumps(details, ensure_ascii=False)[:200]}. "
            f"Est-ce qu'une action est nécessaire ? Si oui, laquelle ?",
            fast=True
        )
        send_discord(f"📨 Rapport de {agent}", [
            {"name": "📋 Message",  "value": message,  "inline": False},
            {"name": "🧠 Analyse", "value": analysis, "inline": False},
        ], color=0x3B82F6)

    return jsonify({"status": "received"})

@app.route("/skill_found", methods=["POST"])
def skill_found():
    """Skills Hunter a trouvé un nouveau skill"""
    if not check_secret():
        return jsonify({"error": "Unauthorized"}), 401
    data  = request.json
    title = data.get("title", "")
    desc  = data.get("description", "")
    score = data.get("security_score", 0)
    url   = data.get("url", "")

    print(f"🔍 Nouveau skill reçu : {title} (score: {score})")

    # Analyse Groq pertinence
    relevance = analyze_skill(title, desc)

    send_decision(
        f"Nouveau skill : {title[:40]}",
        f"🔗 {url}\n📝 {desc[:150]}\n\n"
        f"🔒 Sécurité : **{score}/100**\n"
        f"🧠 **Pertinence IA** : {relevance}\n\n"
        f"💡 Intégrer en paper trading ?",
        action_type="integrate_skill",
        action_data={"title": title, "url": url, "score": score},
        color=0x2ECC71
    )
    return jsonify({"status": "received", "analysis": relevance})

@app.route("/trade_signal", methods=["POST"])
def trade_signal():
    """Trading Agent propose un signal"""
    if not check_secret():
        return jsonify({"error": "Unauthorized"}), 401
    data   = request.json
    symbol = data.get("symbol", "")
    action = data.get("action", "")
    price  = data.get("price", 0)
    amount = data.get("amount", 0)
    reason = data.get("reason", "")

    print(f"📈 Signal reçu : {action} {symbol} @ {price}")

    send_decision(
        f"{action.upper()} {symbol}",
        f"📈 **Signal** : {action.upper()} **{symbol}**\n"
        f"💰 Prix : **{price}$** | Montant : **{amount}€**\n"
        f"💡 Raison : {reason}\n\n"
        f"⚠️ Confirmes-tu cet ordre ?",
        action_type=f"trade_{action}",
        action_data={"symbol": symbol, "action": action,
                     "price": price, "amount": amount},
        color=0x2ECC71 if action == "buy" else 0xE74C3C
    )
    return jsonify({"status": "received"})

# ─── PLANIFICATION ────────────────────────────────────────
def setup_schedule():
    schedule.every().day.at("09:00").do(morning_report)
    schedule.every().day.at("20:00").do(evening_report)
    schedule.every().monday.at("08:00").do(weekly_report)
    schedule.every().monday.at("08:30").do(samet_weekly_tasks)
    schedule.every().hour.do(check_dips)
    schedule.every().hour.do(check_systems)
    schedule.every(6).hours.do(auto_coordinate)
    schedule.every().day.at("08:00").do(
        lambda: (weekly_report() if datetime.now().weekday() == 0 else None)
    )
    print("⏰ Schedule configuré : matin/soir/hebdo/dips/surveillance")

# ─── MAIN ─────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print(f"🛡️  SENTINEL — MANAGER AGENT v{VERSION}")
    print(f"🕐  Démarré le {now_str()}")
    print(f"🧠  LLM : Groq {GROQ_MODEL}")
    print("=" * 55)

    send_discord("🚀 SENTINEL Manager — Opérationnel", [
        {"name": "✅ Status",     "value": "Online H24 sur Railway",    "inline": True},
        {"name": "🧠 LLM",       "value": f"Groq {GROQ_MODEL_FAST}",   "inline": True},
        {"name": "📋 Rôle",
         "value": "• Analyse marché via IA\n"
                  "• Coordonne Skills Hunter + Trading Agent\n"
                  "• Propose décisions → Samet valide ✅/❌\n"
                  "• Rapports matin / soir / hebdo",
         "inline": False},
        {"name": "🔗 Agents", "value":
            f"Skills Hunter : {SKILLS_URL}\n"
            f"Trading Agent : {TRADING_URL}",
         "inline": False},
    ], color=0x2ECC71)

    setup_schedule()

    # Thread Flask pour API inter-agents
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=5001, debug=False),
        daemon=True
    )
    flask_thread.start()
    print("🌐 API Manager démarrée sur port 5001")

    morning_report()

    while True:
        schedule.run_pending()
        time.sleep(60)
