# 🚀 Déploiement Manager Agent sur Railway

## Structure des fichiers
```
manager-agent/
├── manager_agent.py   # Agent principal
├── requirements.txt   # Dépendances Python
├── Procfile           # Commande Railway
└── README.md          # Ce guide
```

---

## ⚙️ Étape 1 — Préparer les fichiers

Crée un dossier `manager-agent` sur ton PC avec ces 3 fichiers.

---

## 📦 Étape 2 — Créer un repo GitHub

```bash
cd manager-agent
git init
git add .
git commit -m "Manager Agent initial"
git branch -M main
git remote add origin https://github.com/TON_USERNAME/halal-manager-agent.git
git push -u origin main
```

---

## 🚂 Étape 3 — Déployer sur Railway

1. Va sur **railway.app** → connecte-toi
2. Clique **"New Project"**
3. Choisis **"Deploy from GitHub repo"**
4. Sélectionne `halal-manager-agent`
5. Railway détecte automatiquement le Procfile ✅

---

## 🔐 Étape 4 — Ajouter les variables d'environnement

Dans Railway → ton projet → **"Variables"** → ajoute :

| Variable | Valeur |
|---|---|
| `DISCORD_WEBHOOK_URL` | Ton webhook Discord |

**Créer le webhook Discord :**
1. Ton serveur Discord → channel #manager
2. Paramètres → Intégrations → Webhooks
3. Nouveau webhook → Copier l'URL

---

## ✅ Étape 5 — Vérifier le déploiement

Dans Railway → **"Logs"** → tu dois voir :
```
📊 Manager Agent démarré sur Railway ✅
⏰ Schedule configuré :
  ☀️  Rapport matin    → 09:00 chaque jour
  🌙  Rapport soir     → 20:00 chaque jour
  🔍  Vérif dips       → chaque heure
```

Et sur Discord → message de démarrage reçu ✅

---

## 📅 Ce que tu reçois sur Discord

| Quand | Rapport |
|---|---|
| Démarrage | ✅ Confirmation Railway online |
| 09:00 chaque jour | ☀️ Rapport matinal (marchés + conseil) |
| 20:00 chaque jour | 🌙 Bilan de la journée |
| Chaque heure | 🟡 Alerte si dip > 3% |
| Lundi 08:00 | 📋 Rapport hebdomadaire |
| 1er du mois 08:00 | 📊 Rapport mensuel complet |

---

## 💰 Coût Railway

- Plan **Hobby** : ~5$/mois (500h/mois)
- Plan **Pro** : ~20$/mois (illimité)

Pour démarrer → **Hobby suffit largement** pour le Manager Agent.
