# Studio IA — APK Android (Capacitor)

> Documentation exhaustive pour développeur·euse : comment transformer la PWA
> `agents/pwa/` en un **fichier `.apk` installable** sur Android.

---

## Table des matières

1. [Ce que ce dossier produit](#1-ce-que-ce-dossier-produit)
2. [Architecture](#2-architecture)
3. [Prérequis](#3-prérequis)
4. [Installation rapide (Replit)](#4-installation-rapide-replit)
5. [Mode 100 % local sans Replit](#5-mode-100--local-sans-replit)
6. [Installation sur votre machine](#6-installation-sur-votre-machine)
7. [Configuration de l'URL API](#7-configuration-de-lurl-api)
8. [Build debug](#8-build-debug)
9. [Build release](#9-build-release)
10. [Signer un APK release](#10-signer-un-apk-release)
11. [Installer sur un téléphone](#11-installer-sur-un-téléphone)
12. [Fichiers et rôles](#12-fichiers-et-rôles)
13. [Build automatisé (CI/CD)](#13-build-automatisé-cicd)
14. [Dépannage](#14-dépannage)
15. [Différences PWA vs APK](#15-différences-pwa-vs-apk)
16. [Sécurité](#16-sécurité)

---

## 1. Ce que ce dossier produit

Ce dossier (`agents/mobile-apk/`) prend les fichiers de la **PWA** (`agents/pwa/`)
et les empaquette dans une **application Android native** grâce à
[Capacitor](https://capacitorjs.com/). Le résultat est un fichier :

```
dist/studio-ia-regie-debug.apk
```

que l'on peut transférer sur un téléphone Android et installer directement
(sans Google Play).

> **Pourquoi Capacitor ?**  
> La PWA est déjà écrite en HTML/CSS/JS vanilla. Capacitor est le moyen le plus
> léger et le plus standard de la transformer en APK : il crée une coquille
> Android native qui affiche la PWA dans une WebView, tout en conservant le
> code web intact et maintenable.

---

## 2. Architecture

```text
┌─────────────────────────────────────────┐
│  Téléphone Android                      │
│  ┌─────────────────────────────────┐    │
│  │  APK Studio IA                  │    │
│  │  ┌─────────────────────────┐    │    │
│  │  │  Android WebView        │    │    │
│  │  │  ┌─────────────────┐    │    │    │
│  │  │  │  PWA embarquée  │    │    │    │
│  │  │  │  (index.html,   │    │    │    │
│  │  │  │   app.js, CSS)  │    │    │    │
│  │  │  └─────────────────┘    │    │    │
│  │  └─────────────────────────┘    │    │
│  └─────────────────────────────────┘    │
│              │ fetch JSON               │
│              ▼                          │
│  Serveur API (Python) sur le réseau   │
│  http://IP:8000  ou  https://...        │
└─────────────────────────────────────────┘
```

**Points clés :**

- Le code UI reste dans `www/` (copie/adaptation de `agents/pwa/`).
- L'APK ne contient **pas** le modèle LLM ni l'API : il se connecte à un
  serveur `api_serveur.py` déjà en cours d'exécution sur le réseau local.
- Les appels API (connexion, productions, pilotage…) passent par HTTP/JSON,
  exactement comme la PWA web.

---

## 3. Prérequis

### 3.1 Outils système

| Outil | Version recommandée | Rôle |
|-------|---------------------|------|
| Node.js | 18+ | Exécuter Capacitor et le CLI |
| npm | 9+ | Installer les dépendances |
| JDK | 17 | Compiler le projet Android |
| Android SDK | API 34, build-tools 34.0.0 | Produire le APK |
| Python | 3.11+ | Lancer `build_apk.py` (facultatif, on peut aussi utiliser npm directement) |

### 3.2 Variables d'environnement

```bash
export JAVA_HOME=/chemin/vers/jdk-17
export ANDROID_HOME=/chemin/vers/android-sdk
export ANDROID_SDK_ROOT=$ANDROID_HOME
export PATH=$ANDROID_HOME/platform-tools:$ANDROID_HOME/build-tools/34.0.0:$PATH
```

### 3.3 Replit (environnement géré)

Sur Replit, tout est fourni par `shell.nix` (JDK 17 + Android SDK minimal).
Aucune installation manuelle.

---

## 4. Installation rapide (Replit)

```bash
# 1. Entrer dans le dossier mobile
cd agents/mobile-apk

# 2. Ouvrir un shell avec JDK + Android SDK
nix-shell shell.nix

# 3. Lancer le build
python build_apk.py --api-url http://192.168.1.42:8000
```

Après le build, le fichier est :

```
agents/mobile-apk/dist/studio-ia-regie-debug.apk
```

> Remplacez `192.168.1.42:8000` par l'IP et le port de la machine qui fait tourner
> `api_serveur.py`. Voir la section 6.

---

## 5. Mode 100 % local sans Replit

### 5.1 Le problème avec le cloud Replit

Replit est excellent pour **développer** et **générer** l'APK, mais l'API qui
tourne dans l'environnement Replit n'est pas joignable directement depuis votre
téléphone. Pour utiliser l'APK au quotidien, il faut donc faire tourner l'API sur
un **PC local** (Windows, Linux ou macOS) et que le téléphone soit sur le même
réseau Wi-Fi.

### 5.2 Exporter le Studio IA sur votre PC

Un script prépare une archive autonome, sans données de production :

```bash
cd agents
python export_local.py
```

Résultat à la racine du projet :

```
studio-ia-local.zip   (environ 0,5 Mo)
```

Décompressez ce fichier sur votre PC. Vous obtenez un dossier `agents/` contenant
tout le code source.

### 5.3 Installer les dépendances sur le PC

**Python :**

```bash
cd agents
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# ou .venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

> S'il n'y a pas de `requirements.txt`, installez les bibliothèques listées dans
> `agents/README.md` (en général : requests, beautifulsoup4, flask, etc.).

**Node.js + npm :** téléchargez la LTS sur https://nodejs.org/.

**JDK 17 + Android SDK :** voir la section 5.4 ci-dessous.

### 5.4 Lancer l'API et générer l'APK

Sur le PC local :

```bash
cd agents
source .venv/bin/activate

# Lancer l'API sur toutes les interfaces réseau
python api_serveur.py --hote 0.0.0.0 --port 8000
```

Dans un autre terminal :

```bash
cd agents/mobile-apk
python build_apk.py --api-url http://<IP-du-PC>:8000
```

Le APK est produit dans `agents/mobile-apk/dist/` et peut être installé sur le
téléphone.

### 5.5 Résumé du flux local

```
PC local
  ├── API Python (api_serveur.py) ← agent Studio IA
  └── Build APK (build_apk.py)
           │
           │  http://IP-du-PC:8000  (même Wi-Fi)
           ▼
Téléphone Android
  └── APK Studio IA
```

Aucune dépendance à Replit n'est nécessaire une fois le code exporté.

---

## 6. Installation sur votre machine

### 6.1 Ubuntu / Debian

```bash
# JDK 17
sudo apt update
sudo apt install openjdk-17-jdk

# Android SDK (command line tools)
mkdir -p ~/Android/cmdline-tools
cd ~/Android/cmdline-tools
wget https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
unzip commandlinetools-linux-*.zip
mv cmdline-tools latest

export ANDROID_HOME=$HOME/Android
export ANDROID_SDK_ROOT=$ANDROID_HOME
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$PATH

# Installer les packages nécessaires
sdkmanager --install "platform-tools" "build-tools;34.0.0" "platforms;android-34"
```

### 6.2 macOS (Homebrew)

```bash
brew install openjdk@17 android-commandlinetools

export ANDROID_HOME=$HOME/Library/Android/sdk
export ANDROID_SDK_ROOT=$ANDROID_HOME
export PATH=$ANDROID_HOME/platform-tools:$ANDROID_HOME/build-tools/34.0.0:$PATH

sdkmanager --install "platform-tools" "build-tools;34.0.0" "platforms;android-34"
```

### 6.3 Windows

1. Installer **Android Studio**.
2. Dans Android Studio → SDK Manager, installer :
   - Android SDK Platform 34
   - Android SDK Build-Tools 34
3. Notez le chemin du SDK (souvent `C:\Users\<vous>\AppData\Local\Android\Sdk`).
4. Définir `ANDROID_HOME` et ajouter `platform-tools` au PATH.

---

## 7. Configuration de l'URL API

L'APK embarque les fichiers web, mais **doit connaître l'adresse du serveur API**
pour fonctionner. Cette adresse est injectée dans `www/config.js` au moment du
build.

### 7.1 Fichier `www/config.js`

```javascript
window.API_BASE_URL = ""; // mode web (même origine)
```

Pour un APK, `build_apk.py` réécrit automatiquement cette ligne :

```javascript
window.API_BASE_URL = "http://192.168.1.42:8000";
```

### 7.2 Trouver l'adresse de l'API

Sur la machine qui fait tourner l'API :

```bash
# Lancer l'API sur toutes les interfaces réseau
python api_serveur.py --hote 0.0.0.0 --port 8000

# Récupérer l'IP locale
ip addr | grep "inet " | grep -v 127
```

### 7.3 Règles de réseau

- Le téléphone et le serveur doivent être sur le **même réseau Wi-Fi**.
- Le pare-feu du serveur doit autoriser le port `8000`.
- En 4G/5G, l'API doit être exposée publiquement avec HTTPS (reverse-proxy ou
tunnel) et l'URL correspondante doit être utilisée.

---

## 8. Build debug

Le build debug est le plus rapide et ne nécessite pas de signature. C'est la
voie recommandée pour les tests.

```bash
cd agents/mobile-apk
nix-shell shell.nix --run 'python build_apk.py --api-url http://192.168.1.42:8000'
```

Équivalent sans `build_apk.py` :

```bash
cd agents/mobile-apk
npm install
npx cap add android
npx cap sync android
cd android && ./gradlew assembleDebug
```

Résultat :

```
android/app/build/outputs/apk/debug/app-debug.apk
```

copié dans :

```
dist/studio-ia-regie-debug.apk
```

---

## 9. Build release

Le build release produit un APK plus petit et optimisé, mais **non signé** par
défaut. Android refuse d'installer un APK release non signé ; il faut le signer
(voir section 9).

```bash
cd agents/mobile-apk
nix-shell shell.nix --run 'python build_apk.py --release --api-url http://192.168.1.42:8000'
```

Résultat :

```
dist/studio-ia-regie-release-unsigned.apk
```

> **Pourquoi non signé ?**  
> La signature requiert un keystore (fichier de certificat) que nous ne créons
> pas automatiquement pour éviter de générer des clés jetables dans le dépôt.
> Créez votre keystore une fois (section 9), puis signez chaque release.

---

## 10. Signer un APK release

### 10.1 Créer un keystore (une seule fois)

```bash
cd agents/mobile-apk
keytool -genkey -v \
  -keystore studio-ia.keystore \
  -alias studio-ia \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000
```

Répondez aux questions. Le mot de passe du keystore sera demandé à chaque build.

> **Conservez ce fichier en lieu sûr.** Sans le keystore et son mot de passe,
> vous ne pourrez plus publier de mises à jour signées avec la même identité.

### 10.2 Signer l'APK

```bash
cd agents/mobile-apk

# Aligner le APK (optimisation obligatoire avant signature)
zipalign -v -p 4 \
  dist/studio-ia-regie-release-unsigned.apk \
  dist/studio-ia-regie-release-aligned.apk

# Signer avec apksigner (fourni par build-tools 34)
apksigner sign \
  --ks studio-ia.keystore \
  --ks-pass pass:<mot-de-passe-keystore> \
  --key-pass pass:<mot-de-passe-clé> \
  --out dist/studio-ia-regie-release.apk \
  dist/studio-ia-regie-release-aligned.apk

# Vérifier
apksigner verify dist/studio-ia-regie-release.apk
```

### 10.3 Automatiser la signature

Vous pouvez ajouter dans `build_apk.py` (ou dans un script CI) les étapes
`zipalign` + `apksigner` après le build release. Gardez le mot de passe dans une
variable d'environnement, jamais dans le dépôt.

---

## 11. Installer sur un téléphone

### 11.1 Par USB (adb)

```bash
# Brancher le téléphone, activer le mode développeur + débogage USB
adb devices
adb install -r dist/studio-ia-regie-debug.apk
```

### 11.2 Par transfert de fichier

1. Copier le APK sur le téléphone (Bluetooth, cable, cloud, etc.).
2. Ouvrir le fichier depuis le téléphone.
3. Android demande l'autorisation d'installer des apps « sources inconnues » :
   accordez-la pour l'application de fichiers utilisée.
4. L'app s'installe et apparaît dans le lanceur.

### 11.3 Premier lancement

1. Assurez-vous que `api_serveur.py` tourne sur le réseau.
2. Ouvrez l'app.
3. Connectez-vous avec un compte existant (créé via `securite.py` ou la CLI).

---

## 12. Fichiers et rôles

```text
agents/mobile-apk/
├── build_apk.py              # Script principal de build
├── capacitor.config.json     # Identité de l'app + dossier web
├── shell.nix                 # Environnement Nix (JDK 17 + Android SDK)
├── package.json              # Dépendances Capacitor
├── README.md                 # Ce document
├── www/                      # Fichiers web embarqués dans le APK
│   ├── index.html            # Page unique (adaptée pour chemins relatifs)
│   ├── app.js                # Logique de la régie (adaptée pour l'APK)
│   ├── config.js             # URL de l'API (injectée au build)
│   ├── style.css             # Thème régie (copie de agents/pwa/style.css)
│   ├── manifest.webmanifest  # Manifeste PWA (adapté)
│   ├── sw.js                 # Service worker (désactivé dans le APK natif)
│   └── icons/                # Icônes de l'app
├── android/                  # Projet Android généré par Capacitor
│   └── app/build.gradle      # Configuration de build (version, SDK, etc.)
└── dist/                     # APK produits
```

### 12.1 `build_apk.py`

Script Python qui orchestre tout le build. Il vérifie les prérequis, installe
les dépendances Node, configure l'API, synchronise les ressources avec Android,
puis lance Gradle.

Options :

| Option | Description |
|--------|-------------|
| `--api-url URL` | URL de l'API à injecter dans `www/config.js` |
| `--release` | Build release (APK non signé) |
| `--clean` | Supprime `android/`, `node_modules/` et `dist/` avant de rebuild |

### 12.2 `capacitor.config.json`

```json
{
  "appId": "fr.studioia.regie",
  "appName": "Studio IA — Régie",
  "webDir": "www",
  "server": {
    "androidScheme": "http",
    "allowNavigation": ["*"]
  }
}
```

- `appId` : identifiant unique Android. À personnaliser si vous publiez.
- `webDir` : dossier des fichiers web embarqués.
- `allowNavigation`: autorise la WebView à naviguer vers n'importe quelle URL
  (nécessaire pour atteindre l'API distante).

### 12.3 `www/app.js` vs `agents/pwa/app.js`

`www/app.js` est une copie adaptée :

- Ajout de `const API_BASE_URL = window.API_BASE_URL || "";`.
- Les appels `fetch(chemin, …)` deviennent `fetch(API_BASE_URL + chemin, …)`.
- Détection de l'environnement natif Capacitor pour **désactiver le service
  worker** dans le APK (il est inutile et source de problèmes avec les fichiers
  locaux).

### 12.4 `www/config.js`

Point de configuration unique. Lors d'un build APK, `build_apk.py` injecte ici
l'URL de l'API. En mode web, ce fichier reste vide (`""`) pour conserver le
comportement « même origine » de la PWA originale.

---

## 13. Build automatisé (CI/CD)

### 13.1 GitHub Actions

Vous pouvez générer le APK automatiquement à chaque push. Exemple de workflow
`.github/workflows/build-apk.yml` :

```yaml
name: Build Studio IA APK

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup JDK 17
        uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: 'temurin'

      - name: Setup Android SDK
        uses: android-actions/setup-android@v3
        with:
          cmdline-tools-version: '11076708'

      - name: Install Android packages
        run: |
          sdkmanager --install "platform-tools" "build-tools;34.0.0" "platforms;android-34"
          echo "ANDROID_HOME=$ANDROID_HOME" >> $GITHUB_ENV

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: agents/mobile-apk/package.json

      - name: Build APK
        working-directory: agents/mobile-apk
        env:
          API_URL: ${{ vars.STUDIO_API_URL }}
        run: |
          npm install
          npx cap add android || true
          npx cap sync android
          sed -i "s|window.API_BASE_URL = \"[^\"]*\";|window.API_BASE_URL = \"$API_URL\";|" www/config.js
          cd android && ./gradlew assembleDebug

      - name: Upload APK
        uses: actions/upload-artifact@v4
        with:
          name: studio-ia-apk
          path: agents/mobile-apk/android/app/build/outputs/apk/debug/app-debug.apk
```

### 13.2 Notes CI/CD

- Stockez `API_URL` dans les variables de dépôt GitHub (`vars.STUDIO_API_URL`).
- Pour le build release, ajoutez la création du keystore et la signature dans des
  secrets GitHub (`secrets.KEYSTORE_BASE64`, `secrets.KEYSTORE_PASSWORD`).
- N'commitez jamais le keystore en clair.

---

## 14. Dépannage

### 14.1 « Java non trouvé »

```
✗ ERREUR : Java non trouvé. Définissez JAVA_HOME ou lancez `nix-shell shell.nix`.
```

**Solution :** lancer le build dans le shell Nix ou installer JDK 17 et définir
`JAVA_HOME`.

### 14.2 « Android SDK non trouvé »

```
✗ ERREUR : Android SDK non trouvé. Définissez ANDROID_HOME [...]
```

**Solution :** vérifier `ANDROID_HOME` et la présence de `build-tools/34.0.0`.

### 14.3 Gradle échoue avec une erreur de licence SDK

L'Android SDK de Nix exige d'accepter la licence. Le `shell.nix` inclut
`config.android_sdk.accept_license = true;`. Si vous utilisez votre propre SDK,
acceptez les licences avec :

```bash
sdkmanager --licenses
```

### 14.4 L'APK s'installe mais ne se connecte pas

1. Vérifiez l'URL dans `www/config.js` (doit être `http://IP:PORT` du serveur).
2. Vérifiez que le téléphone et le serveur sont sur le même réseau.
3. Vérifiez que le pare-feu du serveur autorise le port 8000.
4. Vérifiez que `api_serveur.py` a été lancé avec `--hote 0.0.0.0` (pas `127.0.0.1`).
5. Ouvrez les outils de développement Android (`chrome://inspect` sur un PC
   connecté au téléphone) pour voir les erreurs réseau dans la WebView.

### 14.5 L'APK est trop gros

Le APK debug fait environ 3,6 Mo. Si vous constatez une taille anormale :

- Vérifiez que `www/` ne contient pas de fichiers inutiles (vidéos, gros assets).
- Passez en build release.
- Utilisez Android App Bundle (AAB) pour Google Play au lieu d'un APK brut.

### 14.6 L'APK s'installe mais l'écran reste blanc

1. Ouvrez les logs Android : `adb logcat`.
2. Vérifiez que `config.js` est bien chargé avant `app.js` dans `index.html`.
3. Vérifiez que `capacitor.config.json` pointe bien vers `www`.

---

## 15. Différences PWA vs APK

| Aspect | PWA web | APK Capacitor |
|--------|---------|---------------|
| Installation | Ajout à l'écran d'accueil via navigateur | Fichier `.apk` installé comme une app native |
| Hors-ligne | Oui, grâce au service worker | Oui, fichiers embarqués dans l'APK |
| Accès réseau | Même origine par défaut | URL distante configurée dans `config.js` |
| Service worker | Actif | Désactivé (inutile en natif) |
| Mise à jour UI | Rafraîchir la page | Réinstaller le APK (ou utiliser Capacitor Live Update) |
| Certificat | Nécessite HTTPS pour l'installation | Aucun (sauf si l'API est en HTTPS) |
| API distante | Possible avec CORS | Possible avec `allowNavigation` |

---

## 16. Sécurité

- **Ne commitez jamais le keystore** (`studio-ia.keystore`).
- **Ne commitez jamais de mot de passe** en clair.
- L'APK embarque le code web mais **pas** les secrets. Les secrets restent côté
  serveur (`api_serveur.py`, `securite.py`).
- Le jeton de session est stocké dans `localStorage` comme dans la PWA. Sur un
  téléphone rooté, cela peut être lu ; considérez l'appareil comme un client
  normal.
- En production, servez l'API en HTTPS, même en réseau local, pour éviter le
  vol de jeton sur un Wi-Fi partagé.

---

## Résumé rapide

```bash
cd agents/mobile-apk
nix-shell shell.nix --run 'python build_apk.py --api-url http://<IP_SERVEUR>:8000'
# APK dans dist/studio-ia-regie-debug.apk
```

Pour toute question, consultez d'abord la section 13 (Dépannage) et vérifiez
que le serveur API est bien accessible depuis le téléphone.
