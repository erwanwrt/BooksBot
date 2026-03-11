# BooksBot

Bot Telegram personnel pour rechercher et telecharger des ebooks (EPUB) depuis [Anna's Archive](https://annas-archive.org), avec livraison directe sur Telegram ou sur Kindle.

Inspire par le projet [maman-books](https://github.com/Zoeille/maman-books) de Zoeille.

## Fonctionnalites

- **Recherche** de livres au format EPUB par titre et langue (FR, EN, ES, DE, IT)
- **Telechargement** automatise via Playwright (bypass DDoS-Guard)
- **Livraison Telegram** : envoi direct du fichier dans le chat (limite 50 Mo)
- **Livraison Kindle** : envoi par email vers votre Kindle (via Gmail SMTP)
- **Livraison double** : Telegram + Kindle simultanement
- **Multi-utilisateurs** : acces restreint a une liste d'IDs Telegram autorises

## Fonctionnement

1. L'utilisateur envoie un titre de livre (ou utilise `/search <titre>`)
2. Le bot propose un choix de langue
3. Il recherche sur Anna's Archive et affiche jusqu'a 10 resultats
4. L'utilisateur choisit un livre puis un mode de livraison
5. Le bot telecharge l'EPUB via un navigateur automatise et le livre

Le navigateur Playwright est necessaire pour contourner les protections DDoS-Guard et le systeme de countdown d'Anna's Archive. Le telechargement depuis les miroirs se fait egalement via le navigateur pour eviter le blocage d'IP de datacenter.

## Installation

### Prerequis

- Python 3.12+
- Un token de bot Telegram (via [@BotFather](https://t.me/BotFather))
- Un mot de passe d'application Gmail (pour l'envoi Kindle)

### Configuration

Copiez `.env.example` en `.env` et remplissez les valeurs :

```env
# Telegram
TELEGRAM_BOT_TOKEN=votre_token
TELEGRAM_USER_ID=123456789,987654321

# Kindle (via Gmail SMTP)
KINDLE_EMAIL=votre_email@kindle.com
SMTP_EMAIL=votre_gmail@gmail.com
SMTP_PASSWORD=votre_mot_de_passe_application

# Anna's Archive (optionnel, pour utiliser un miroir)
ANNAS_ARCHIVE_URL=https://annas-archive.org
```

`TELEGRAM_USER_ID` accepte plusieurs IDs separes par des virgules pour autoriser plusieurs utilisateurs.

### Execution locale

```bash
pip install -r requirements.txt
playwright install --with-deps chromium
python main.py
```

### Deploiement Docker

```bash
docker compose up -d --build
```

Le conteneur inclut Xvfb (serveur d'affichage virtuel) pour faire tourner Chromium. La configuration Docker Compose monte deux volumes persistants :

- `browser_data` : cookies du navigateur (maintient la session DDoS-Guard)
- `downloads` : fichiers telecharges temporairement

## Commandes du bot

| Commande | Description |
|----------|-------------|
| `/start` | Message de bienvenue |
| `/search <titre>` | Rechercher un livre |
| `/cancel` | Annuler la recherche en cours |
| *texte libre* | Lance une recherche automatiquement |

## Structure du projet

```
BooksBot/
├── main.py              # Point d'entree
├── bot.py               # Handlers Telegram et flux de conversation
├── anna_archive.py      # Recherche et telechargement (Playwright)
├── downloader.py        # Utilitaires de telechargement
├── mailer.py            # Envoi Kindle par email (Gmail SMTP)
├── config.py            # Chargement de la configuration
├── requirements.txt     # Dependances Python
├── Dockerfile           # Image Docker
├── docker-compose.yml   # Orchestration Docker
└── .env.example         # Template des variables d'environnement
```

## Disclaimer

Ce projet est fourni **a titre educatif et personnel uniquement**.

L'auteur **ne peut etre tenu responsable** de l'utilisation faite de ce bot, notamment en ce qui concerne le telechargement, la distribution ou la reproduction de contenus proteges par le droit d'auteur. Il appartient a chaque utilisateur de s'assurer que son usage est conforme a la legislation en vigueur dans son pays.

Le telechargement d'oeuvres non libres de droit sans l'accord des ayants droit est illegal dans la plupart des juridictions. **Utilisez ce bot de maniere responsable.**
