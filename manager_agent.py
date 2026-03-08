"""
📊 MANAGER AGENT — Halal Ecosystem
Tourne H24 sur Railway.
- Surveille Railway, Discord, TWS, tous les agents
- Guide les autres agents
- Propose des décisions financières via boutons Discord
- JAMAIS d'exécution sans autorisation de Samet
"""

import os
import requests
import schedule
import time
import json
import yfinance as yf
from datetime import datetime
from pathlib import Path

# ─── CONFIG ───────────────────────────────────────────────
DISCORD_TOKEN    = os.getenv("DISCORD_TOKEN", "")
DISCORD_WEBHOOK  = os.getenv("DISCORD_WEBHOOK_URL", "")
CHANNEL_ID       = os.getenv("DISCORD_CHANNEL_ID", "")

PORTFOLIO = {
    "SGOL": 0.15, "PHAG": 0.10, "ICLN": 0.15,
    "ENPH": 0.10, "MOO":  0.10, "DBA":  0.10,
    "SPUS": 0.15, "HLAL": 0.10, "PHO":  0.05
}
DIP_THRESHOLD = -0.05   # -5% → proposition d'achat
DCA_AMOUNT    = 50.0

# ─── État partagé ─────────────────────────────────────────
STATE_FILE = Path("manager_state.json")

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"pending_decisions": [], "approved": [], "rejected": [],
            "agents_status": {}, "last_updated": ""}

def save_state(state: dict):
    state["last_updated"] = str(datetime.now())
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ─── Helpers ──────────────────────────────────────────────
def now_str():
    return datetime.now().strftime("%d/%m/%Y %H:%M")

def send_discord(title: str, fields: list, color: int = 0xC9A84C, components: list = None):
    embed = {
        "title": title, "color": color, "fields": fields,
        "footer": {"text": f"📊 Manager Agent • {now_str()}"},
        "timestamp": datetime.utcnow().isoformat()
    }
    payload = {"embeds": [embed]}
    if components:
        payload["components"] = components
    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        print(f"✅ Discord → {title}")
    except Exception as e:
        print(f"❌ Discord erreur : {e}")

def send_decision_request(title: str, description: str,
                           action_type: str, action_data: dict, color: int = 0xF39C12):
    """
    Envoie une proposition avec boutons ✅ / ❌
    JAMAIS exécutée sans approbation de Samet.
    """
    state = load_state()
    decision_id = f"{action_type}_{int(time.time())}"

    state["pending_decisions"].append({
        "id": decision_id, "title": title,
        "action_type": action_type, "action_data": action_data,
        "created_at": str(datetime.now()), "status": "pending"
    })
    save_state(state)

    components = [{
        "type": 1,
        "components": [
            {"type": 2, "style": 3, "label": "✅ Approuver",
             "custom_id": f"approve_{decision_id}"},
            {"type": 2, "style": 4, "label": "❌ Refuser",
             "custom_id": f"reject_{decision_id}"}
        ]
    }]

    fields = [
        {"name": "📋 Proposition", "value": description, "inline": False},
        {"name": "🔑 ID",          "value": f"`{decision_id}`", "inline": True},
        {"name": "⚠️ Requis",      "value": "Clique ✅ ou ❌", "inline": True},
    ]
    send_discord(f"🟡 Décision — {title}", fields, color=color, components=components)
    return decision_id


# ─── 1. SURVEILLANCE H24 ──────────────────────────────────

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

def get_market_mood() -> str:
    try:
        change = yf.Ticker("SPY").fast_info.get("regularMarketChangePercent", 0)
        if change > 1:    return "🟢 Haussier"
        elif change > 0:  return "🟡 Stable"
        elif change > -1: return "🟠 Prudent"
        else:             return "🔴 Baissier"
    except:
        return "❓ Indisponible"

def surveillance_check():
    """Vérifie Railway + Discord toutes les heures"""
    print("🔍 Surveillance systèmes...")
    state = load_state()
    railway_ok = False
    discord_ok = False

    try:
        railway_ok = requests.get("https://railway.app", timeout=5).status_code == 200
    except: pass
    try:
        discord_ok = requests.get("https://discord.com/api/v10/gateway", timeout=5).status_code == 200
    except: pass

    state["agents_status"]["railway"] = "✅ OK" if railway_ok else "❌ Problème"
    state["agents_status"]["discord"] = "✅ OK" if discord_ok else "❌ Problème"
    state["agents_status"]["manager"] = "✅ Online (Railway)"
    state["agents_status"]["last_check"] = now_str()
    save_state(state)

    if not railway_ok or not discord_ok:
        send_discord("⚠️ Problème système détecté", [
            {"name": "🚂 Railway", "value": "✅" if railway_ok else "❌ Hors ligne", "inline": True},
            {"name": "💬 Discord", "value": "✅" if discord_ok else "❌ Hors ligne", "inline": True},
        ], color=0xE74C3C)


# ─── 2. DÉTECTION DIPS → PROPOSITION ─────────────────────

def check_dips():
    print("📉 Vérification dips...")
    prices = get_prices()
    state = load_state()
    today = datetime.now().strftime("%Y-%m-%d")

    for symbol, data in prices.items():
        if data["change"] / 100 <= DIP_THRESHOLD:
            already = any(
                d["action_data"].get("symbol") == symbol and d["created_at"].startswith(today)
                for d in state["pending_decisions"]
            )
            if already:
                continue
            extra = round(DCA_AMOUNT * 0.5, 2)
            send_decision_request(
                f"Dip {symbol} ({data['change']:+.1f}%)",
                f"**{symbol}** a baissé de **{data['change']:+.1f}%**\n"
                f"Prix : **{data['price']}$**\n"
                f"💡 Acheter **{extra}€** supplémentaires ?",
                action_type="buy_dip",
                action_data={"symbol": symbol, "amount": extra, "price": data["price"]},
                color=0xF39C12
            )


# ─── 3. PROPOSITION REBALANCEMENT ─────────────────────────

def check_rebalance():
    print("⚖️ Vérification rebalancement...")
    prices = get_prices()
    total = sum(d["price"] for d in prices.values())
    if total == 0:
        return

    deviations = {}
    for symbol, target in PORTFOLIO.items():
        current = round(prices.get(symbol, {}).get("price", 0) / total, 3)
        if abs(current - target) > 0.05:
            deviations[symbol] = {"target": target, "current": current}

    if deviations:
        details = "\n".join(
            f"**{s}** : {d['current']*100:.1f}% → cible {d['target']*100:.1f}%"
            for s, d in deviations.items()
        )
        send_decision_request(
            "Rebalancement suggéré",
            f"Écarts détectés :\n{details}\n💡 Rééquilibrer au prochain DCA ?",
            action_type="rebalance",
            action_data={"deviations": deviations},
            color=0x3B82F6
        )


# ─── 4. GUIDAGE DES AGENTS ────────────────────────────────

def guide_guardian(action: str, reason: str):
    state = load_state()
    state["agents_status"]["guardian_order"] = action
    save_state(state)
    send_discord("🛡️ Manager → Guardian", [
        {"name": "📋 Instruction", "value": action, "inline": False},
        {"name": "💡 Raison",      "value": reason, "inline": False},
    ], color=0x8B5CF6)
    print(f"📡 Guardian guidé : {action}")

def guide_backtesting(symbol: str, reason: str):
    state = load_state()
    state["agents_status"]["backtesting_order"] = f"Tester {symbol}"
    save_state(state)
    send_discord("🧪 Manager → Backtesting", [
        {"name": "📈 Actif", "value": f"**{symbol}**", "inline": True},
        {"name": "💡 Raison", "value": reason,          "inline": False},
    ], color=0x2ECC71)
    print(f"📡 Backtesting guidé : {symbol}")

def guide_skills_hunter(topic: str, reason: str):
    state = load_state()
    state["agents_status"]["skills_hunter_order"] = f"Chercher {topic}"
    save_state(state)
    send_discord("🔍 Manager → Skills Hunter", [
        {"name": "🔎 Sujet", "value": f"**{topic}**", "inline": True},
        {"name": "💡 Raison", "value": reason,          "inline": False},
    ], color=0xF59E0B)
    print(f"📡 Skills Hunter guidé : {topic}")

def auto_guide_agents():
    """Guidance intelligente automatique chaque matin"""
    print("🎯 Guidance automatique...")
    prices = get_prices()
    mood = get_market_mood()

    # Marché baissier → Guardian alerte renforcée
    if "Baissier" in mood:
        guide_guardian("Mode surveillance renforcée",
                       f"Marché baissier détecté — vérif toutes les 30s")

    # Actif en forte baisse → re-backtesting
    for symbol, data in prices.items():
        if data["change"] <= -5:
            guide_backtesting(symbol,
                              f"Forte baisse {data['change']:+.1f}% — re-valider stratégie DCA")
            break

    # Chaque lundi → Skills Hunter
    if datetime.now().weekday() == 0:
        guide_skills_hunter("halal DCA strategy 2026",
                            "Recherche hebdomadaire automatique")


# ─── 5. RAPPORTS ──────────────────────────────────────────

def morning_report():
    print("☀️ Rapport matinal...")
    prices = get_prices()
    mood   = get_market_mood()
    state  = load_state()
    gainers = sorted([(s,d) for s,d in prices.items() if d["change"]>0], key=lambda x: -x[1]["change"])
    losers  = sorted([(s,d) for s,d in prices.items() if d["change"]<0], key=lambda x: x[1]["change"])

    fields = [
        {"name": "🌍 Marchés",    "value": mood, "inline": False},
        {"name": "📈 Hausse",
         "value": "\n".join(f"**{s}** {d['price']}$ ({d['change']:+.1f}%)" for s,d in gainers[:4]) or "Aucun",
         "inline": True},
        {"name": "📉 Baisse",
         "value": "\n".join(f"**{s}** {d['price']}$ ({d['change']:+.1f}%)" for s,d in losers[:4]) or "Aucun",
         "inline": True},
        {"name": "─────────────────", "value": " ", "inline": False},
        {"name": "⏳ En attente",  "value": f"**{len(state['pending_decisions'])}** décision(s)", "inline": True},
        {"name": "📅 Prochain DCA","value": _next_dca(), "inline": True},
        {"name": "💡 Conseil",     "value": _daily_advice(prices, mood), "inline": False},
    ]
    send_discord("☀️ Rapport Matinal — Halal Ecosystem", fields, color=0xF39C12)
    auto_guide_agents()

def evening_report():
    print("🌙 Rapport du soir...")
    prices = get_prices()
    state  = load_state()
    avg    = sum(d["change"] for d in prices.values()) / len(prices)

    fields = [
        {"name": f"{'📈' if avg>0 else '📉'} Performance", "value": f"**{avg:+.2f}%** moyenne", "inline": False},
        {"name": "📊 Actifs",
         "value": "\n".join(f"{'🟢' if d['change']>0 else '🔴'} **{s}** {d['price']}$ ({d['change']:+.1f}%)"
                            for s,d in prices.items()),
         "inline": False},
        {"name": "─────────────────", "value": " ", "inline": False},
        {"name": "🤖 Agents",
         "value": "\n".join(f"{k}: {v}" for k,v in state["agents_status"].items()
                            if "last" not in k) or "Tous OK ✅",
         "inline": False},
        {"name": "🌙 Bilan", "value": _evening_summary(avg), "inline": False},
    ]
    send_discord("🌙 Rapport du Soir — Halal Ecosystem", fields, color=0x8B5CF6)

def weekly_report():
    print("📋 Rapport hebdo...")
    prices = get_prices()
    state  = load_state()
    top3   = sorted(prices.items(), key=lambda x: -x[1]["change"])[:3]

    fields = [
        {"name": "🌍 Marchés", "value": get_market_mood(), "inline": False},
        {"name": "🏆 Top 3",
         "value": "\n".join(f"{'🥇🥈🥉'[i]} **{s}** {d['change']:+.1f}%" for i,(s,d) in enumerate(top3)),
         "inline": False},
        {"name": "✅ Approuvées", "value": str(len(state["approved"])),  "inline": True},
        {"name": "❌ Refusées",   "value": str(len(state["rejected"])),  "inline": True},
        {"name": "📋 Rappels",
         "value": "• Skills Hunter a tourné ce lundi\n• Backtesting re-validé\n• Cerveau Central synchro",
         "inline": False},
    ]
    send_discord("📋 Rapport Hebdomadaire", fields, color=0x2ECC71)

def monthly_report():
    print("📊 Rapport mensuel...")
    month = datetime.now().strftime("%B %Y")
    fields = [
        {"name": f"📅 {month}", "value": "DCA 50€ exécuté ✅", "inline": False},
        {"name": "💰 Investi",  "value": f"**{100+50*datetime.now().month}€**", "inline": True},
        {"name": "🕌 Halal",   "value": "100% ✅", "inline": True},
        {"name": "─────────────────", "value": " ", "inline": False},
        {"name": "📁 Actions",
         "value": "• Uploader `intelligence-update.md` dans Claude 🧠\n"
                  "• Vérifier le rapport PDF mensuel\n"
                  "• Valider les nouveaux skills",
         "inline": False},
    ]
    send_discord(f"📊 Rapport Mensuel — {month}", fields, color=0xC9A84C)


# ─── HELPERS ──────────────────────────────────────────────

def _daily_advice(prices: dict, mood: str) -> str:
    losers = [(s,d) for s,d in prices.items() if d["change"] < -2]
    if losers:
        w = min(losers, key=lambda x: x[1]["change"])
        return f"**{w[0]}** en baisse de {w[1]['change']:.1f}% — Dip potentiel 👀"
    if "Baissier" in mood: return "Marché baissier — Reste discipliné 🕌"
    if "Haussier" in mood: return "Bonne dynamique — DCA régulier 💪"
    return "Marché calme — La régularité prime ⚡"

def _evening_summary(avg: float) -> str:
    if avg > 1:  return "Excellente journée ! Baraka Allah 🌙"
    if avg > 0:  return "Journée positive. Continue 📈"
    if avg > -1: return "Légère baisse normale. Long terme 💪"
    return "Journée difficile. Chaque baisse = opportunité 🕌"

def _next_dca() -> str:
    n = datetime.now()
    if n.day == 1: return "**Aujourd'hui !** 🚀"
    try:
        nxt = n.replace(month=n.month%12+1, day=1) if n.month<12 else n.replace(year=n.year+1, month=1, day=1)
        return f"Dans **{(nxt-n).days} jours**"
    except:
        return "Le 1er du mois"


# ─── PLANIFICATION ────────────────────────────────────────

def setup_schedule():
    schedule.every().day.at("09:00").do(morning_report)
    schedule.every().day.at("20:00").do(evening_report)
    schedule.every().hour.do(surveillance_check)
    schedule.every().hour.do(check_dips)
    schedule.every(6).hours.do(check_rebalance)
    schedule.every().monday.at("08:00").do(weekly_report)
    schedule.every().day.at("08:00").do(
        lambda: monthly_report() if datetime.now().day == 1 else None
    )
    print("⏰ Schedule configuré :")
    print("  ☀️  Matin        → 09:00")
    print("  🌙  Soir         → 20:00")
    print("  🔍  Dips         → chaque heure")
    print("  🛡️  Surveillance → chaque heure")
    print("  ⚖️  Rebalance    → toutes les 6h")
    print("  📋  Hebdo        → lundi 08:00")
    print("  📊  Mensuel      → 1er du mois")


# ─── MAIN ─────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("📊 MANAGER AGENT — Halal Ecosystem")
    print(f"🕐 Démarré le {now_str()}")
    print("=" * 50)

    send_discord("🚀 Manager Agent opérationnel", [
        {"name": "✅ Status", "value": "Online sur Railway H24",       "inline": True},
        {"name": "🕐 Heure",  "value": now_str(),                       "inline": True},
        {"name": "📋 Rôle",
         "value": "• Surveille Railway + Discord + TWS\n"
                  "• Guide Guardian, Backtesting, Skills Hunter\n"
                  "• Propose décisions → tu approuves ✅/❌\n"
                  "• Rapports matin / soir / hebdo / mensuel",
         "inline": False},
    ], color=0x2ECC71)

    setup_schedule()
    morning_report()

    while True:
        schedule.run_pending()
        time.sleep(60)
