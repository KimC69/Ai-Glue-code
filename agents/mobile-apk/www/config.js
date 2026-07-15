/*
 * config.js — Configuration de l'application mobile Studio IA.
 *
 * Ce fichier est chargé AVANT app.js. Il définit l'URL de base de l'API
 * que l'application appellera.
 *
 *  - En mode web (PWA) : laisser "" pour utiliser la même origine (l'API et
 *    la PWA sont servies par le même serveur Python).
 *  - En mode APK (Capacitor) : build_apk.py injecte ici l'URL de l'API avant
 *    de compiler. Valeur par défaut ci-dessous à personnaliser si besoin.
 */
"use strict";
window.API_BASE_URL = ""; // ex. "http://192.168.1.42:8000"
