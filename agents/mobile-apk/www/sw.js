/*
 * sw.js — Service worker de la régie mobile (PWA, étape 9).
 *
 * Rôle : rendre l'application INSTALLABLE et disponible HORS LIGNE en mettant en
 * cache sa « coquille » statique (HTML, CSS, JS, icônes). Les appels à l'API
 * (données vivantes + authentification) ne sont JAMAIS mis en cache : ils
 * passent toujours par le réseau, sinon on afficherait des données périmées ou
 * on contournerait la sécurité.
 *
 * Rappel : le navigateur n'active un service worker qu'en contexte sécurisé
 * (HTTPS ou localhost). Sur un simple http://IP:port, il est ignoré et l'app
 * reste une page web classique.
 *
 * Note : ce service worker est désactivé dans l'APK Android (Capacitor) car
 * les fichiers sont déjà embarqués localement. Il n'est utile que pour la PWA
 * web servie par l'API.
 */

"use strict";

const CACHE = "studio-ia-v1";
const COQUILLE = [
  "./",
  "./index.html",
  "./style.css",
  "./app.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

// Chemins de l'API : toujours réseau, jamais cache.
const CHEMINS_API = ["/connexion", "/deconnexion", "/productions", "/sante"];
function estAppelAPI(url) {
  return CHEMINS_API.includes(url.pathname) || url.pathname.startsWith("/productions/");
}

self.addEventListener("install", (evt) => {
  evt.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(COQUILLE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (evt) => {
  evt.waitUntil(
    caches.keys()
      .then((cles) => Promise.all(cles.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (evt) => {
  const req = evt.request;
  const url = new URL(req.url);

  // On ne gère que les GET de la coquille (même origine, hors API).
  if (req.method !== "GET" || url.origin !== self.location.origin || estAppelAPI(url)) {
    return; // laissé au comportement réseau par défaut
  }

  // Réseau d'abord (pour récupérer les mises à jour), cache en repli hors ligne.
  evt.respondWith(
    fetch(req)
      .then((rep) => {
        const copie = rep.clone();
        caches.open(CACHE).then((c) => c.put(req, copie)).catch(() => {});
        return rep;
      })
      .catch(() => caches.match(req).then((c) => c || caches.match("./")))
  );
});
