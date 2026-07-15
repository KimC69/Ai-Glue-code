/*
 * app.js — Logique de la régie mobile (PWA + APK Capacitor).
 *
 * Équivalent JavaScript de client_api.py : parle à la MÊME API (api_serveur.py).
 * Le jeton de session est conservé dans localStorage ; il est ajouté en en-tête
 * « Authorization: Bearer <jeton> » sur chaque appel protégé. À la moindre
 * réponse 401, on repasse automatiquement à l'écran de connexion.
 *
 * Cette version supporte deux modes de déploiement :
 *   1. PWA web : servie par le serveur Python, API sur la même origine.
 *   2. APK Android (Capacitor) : fichiers locaux, API distante configurée
 *      dans www/config.js (générée par build_apk.py).
 *
 * Vanilla JS, aucune dépendance obligatoire (Capacitor n'est utilisé que s'il
 * est présent, c'est-à-dire dans l'APK).
 */

"use strict";

// ── Configuration de l'API ─────────────────────────────────────────────────
// En web : "" → même origine. En APK : injecté par build_apk.py dans config.js.
const API_BASE_URL = window.API_BASE_URL || "";
const EST_NATIF = (window.Capacitor && window.Capacitor.isNativePlatform) ? window.Capacitor.isNativePlatform() : false;

// ── État local ───────────────────────────────────────────────────────────
const CLE_JETON = "studio_jeton";
const CLE_ROLE = "studio_role";
const ROLES_LANCEMENT = ["admin", "operateur"]; // droit « lancer_production »
const ROLES_PILOTAGE = ["admin", "operateur"];  // droit « piloter_production »
const ROLES_ADMIN = ["admin"];                    // droit « gerer_utilisateurs »

let productionCourante = null; // id affiché dans la vue détail
let minuteur = null;           // rafraîchissement automatique

const $ = (sel) => document.querySelector(sel);

function jeton() { return localStorage.getItem(CLE_JETON) || ""; }
function role() { return localStorage.getItem(CLE_ROLE) || ""; }

// ── Appels API ─────────────────────────────────────────────────────────────
async function api(methode, chemin, corps) {
  const entetes = { "Accept": "application/json" };
  if (corps !== undefined) entetes["Content-Type"] = "application/json; charset=utf-8";
  const j = jeton();
  if (j) entetes["Authorization"] = "Bearer " + j;

  const url = API_BASE_URL + chemin;

  let rep;
  try {
    rep = await fetch(url, {
      method: methode,
      headers: entetes,
      body: corps !== undefined ? JSON.stringify(corps) : undefined,
    });
  } catch (e) {
    throw { code: 0, message: "Serveur injoignable. Vérifiez la connexion et l'URL de l'API dans config.js." };
  }

  let objet = {};
  try { objet = await rep.json(); } catch (e) { /* corps vide ou non-JSON */ }

  if (!rep.ok) {
    // Jeton expiré/révoqué : on déconnecte proprement plutôt que d'insister.
    if (rep.status === 401 && jeton()) { deconnexionLocale(); afficherVue("connexion"); }
    throw { code: rep.status, message: (objet && objet.erreur) || ("Erreur " + rep.status) };
  }
  return objet;
}

// ── Navigation entre vues ────────────────────────────────────────────────
function afficherVue(nom) {
  for (const v of ["connexion", "tableau", "detail", "agents", "memoire", "chat"]) {
    $("#vue-" + v).hidden = (v !== nom);
  }
  clearInterval(minuteur);
  if (nom === "tableau") minuteur = setInterval(rafraichirListe, 5000);
  if (nom === "detail") minuteur = setInterval(() => afficherDetail(productionCourante, true), 5000);
}

// ── Connexion / déconnexion ────────────────────────────────────────────────
async function seConnecter(evt) {
  evt.preventDefault();
  const btn = $("#btn-connexion");
  const err = $("#erreur-connexion");
  err.hidden = true;
  btn.disabled = true;
  btn.textContent = "Connexion…";
  try {
    const rep = await api("POST", "/connexion", {
      nom: $("#ch-nom").value.trim(),
      mot_de_passe: $("#ch-mdp").value,
    });
    localStorage.setItem(CLE_JETON, rep.jeton || "");
    localStorage.setItem(CLE_ROLE, rep.role || "");
    $("#ch-mdp").value = "";
    entrerTableau();
  } catch (e) {
    err.textContent = e.message;
    err.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Se connecter";
  }
}

function deconnexionLocale() {
  localStorage.removeItem(CLE_JETON);
  localStorage.removeItem(CLE_ROLE);
}

async function seDeconnecter() {
  try { await api("POST", "/deconnexion"); } catch (e) { /* on déconnecte quand même */ }
  deconnexionLocale();
  afficherVue("connexion");
}

// ── Tableau de bord ────────────────────────────────────────────────────────
function entrerTableau() {
  $("#badge-role").textContent = role();
  $("#btn-nouvelle").hidden = !ROLES_LANCEMENT.includes(role());
  // Le chat nécessite « piloter_production » : inutile de le proposer à un
  // simple observateur (il n'obtiendrait qu'un refus 403).
  $("#btn-nav-chat").hidden = !ROLES_PILOTAGE.includes(role());
  afficherVue("tableau");
  rafraichirListe();
}

async function rafraichirListe() {
  try {
    const rep = await api("GET", "/productions");
    const liste = rep.productions || [];
    const conteneur = $("#liste-productions");
    $("#liste-vide").hidden = liste.length > 0;
    conteneur.innerHTML = "";
    for (const p of liste) conteneur.appendChild(carteProduction(p));
  } catch (e) {
    if (e.code !== 401) toast(e.message, "erreur");
  }
}

function carteProduction(p) {
  const el = document.createElement("div");
  el.className = "carte-prod";
  const reussies = p.etapes_reussies != null ? p.etapes_reussies : 0;
  el.innerHTML = `
    <div class="ligne-haut">
      <span class="idee"></span>
      <span class="badge ${classeStatut(p.statut)}">${libelleStatut(p.statut)}</span>
    </div>
    <div class="meta">
      <span>✓ ${reussies} étape(s)</span>
      <span>${formaterDate(p.demarree_le)}</span>
    </div>`;
  el.querySelector(".idee").textContent = p.idee || "(sans titre)";
  el.addEventListener("click", () => afficherDetail(p.id));
  return el;
}

// ── Détail d'une production ─────────────────────────────────────────────────
async function afficherDetail(id, silencieux) {
  productionCourante = id;
  if (!silencieux) afficherVue("detail");
  try {
    const d = await api("GET", "/productions/" + id);
    const p = d.production || {};
    const etapes = d.etapes || [];
    const evenements = d.evenements || [];

    $("#contenu-detail").innerHTML = `
      <div class="bloc">
        <div class="detail-idee"></div>
        <div class="detail-meta">
          <span class="badge ${classeStatut(p.statut)}">${libelleStatut(p.statut)}</span>
          <span>Modèle : ${echapper(p.modele || "défaut")}</span>
          <span>Démarrée : ${formaterDate(p.demarree_le)}</span>
          ${p.terminee_le ? `<span>Terminée : ${formaterDate(p.terminee_le)}</span>` : ""}
        </div>
      </div>
      <div class="bloc" id="detail-controle" hidden></div>
      <div class="bloc">
        <h3>Étapes (${etapes.length})</h3>
        <div id="detail-etapes"></div>
      </div>
      <div class="bloc">
        <h3>Journal / raisonnement (${evenements.length})</h3>
        <div id="detail-evts"></div>
      </div>`;
    $("#contenu-detail .detail-idee").textContent = p.idee || "(sans titre)";
    rendreControles(p);

    const boiteEtapes = $("#detail-etapes");
    if (etapes.length === 0) boiteEtapes.innerHTML = `<p class="etat-vide">Pas encore d'étape.</p>`;
    for (const e of etapes) boiteEtapes.appendChild(ligneEtape(e));

    const boiteEvts = $("#detail-evts");
    if (evenements.length === 0) boiteEvts.innerHTML = `<p class="etat-vide">Aucun événement.</p>`;
    for (const ev of evenements.slice().reverse()) boiteEvts.appendChild(ligneEvenement(ev));
  } catch (e) {
    if (e.code !== 401) toast(e.message, "erreur");
  }
}

function ligneEtape(e) {
  const el = document.createElement("div");
  el.className = "etape";
  const duree = e.duree_s != null ? formaterDuree(e.duree_s) : "";
  el.innerHTML = `
    <span class="num">${e.numero != null ? e.numero : "•"}</span>
    <span class="nom"></span>
    <span class="badge ${classeStatut(e.statut)}">${libelleStatut(e.statut)}</span>
    <span class="duree">${duree}</span>`;
  el.querySelector(".nom").textContent = e.nom || "";
  return el;
}

function ligneEvenement(ev) {
  const el = document.createElement("div");
  el.className = "evt" + (ev.niveau === "critique" ? " critique" : "");
  el.innerHTML = `
    <div class="evt-tete"><span>${echapper(ev.type || "")}</span><span>${formaterHeure(ev.horodatage)}</span></div>
    <div class="evt-msg"></div>`;
  el.querySelector(".evt-msg").textContent = ev.message || "";
  return el;
}

// ── Pilotage à distance (pause / reprise / arrêt) ───────────────────────────
function rendreControles(p) {
  const boite = $("#detail-controle");
  if (!boite) return;
  const actif = ["en_cours", "en_pause"].includes(p.statut || "");
  const pilotable = actif && ROLES_PILOTAGE.includes(role());
  if (!pilotable) { boite.hidden = true; boite.innerHTML = ""; return; }
  boite.hidden = false;
  const enPause = p.statut === "en_pause";
  boite.innerHTML = `
    <h3>Pilotage</h3>
    <p class="note">Une commande prend effet à la fin de l'étape en cours.</p>
    <div class="controle-boutons">
      ${enPause
        ? `<button class="btn btn-principal" data-cmd="reprendre">▶️ Reprendre</button>`
        : `<button class="btn btn-secondaire" data-cmd="pause">⏸️ Pause</button>`}
      <button class="btn btn-danger" data-cmd="arreter">⏹️ Arrêter</button>
    </div>`;
  boite.querySelectorAll("button[data-cmd]").forEach((b) =>
    b.addEventListener("click", () => piloter(p.id, b.dataset.cmd)));
}

async function piloter(id, commande) {
  if (commande === "arreter" &&
      !confirm("Arrêter définitivement cette production ?")) return;
  try {
    const rep = await api("POST", "/productions/" + id + "/" + commande);
    toast(rep.message || "Commande transmise", "succes");
    afficherDetail(id, true);
  } catch (e) { toast(e.message, "erreur"); }
}

// ── Agents (activation / désactivation) ─────────────────────────────────────
async function entrerAgents() { afficherVue("agents"); await chargerAgents(); }

async function chargerAgents() {
  try {
    const rep = await api("GET", "/agents");
    const boite = $("#liste-agents");
    boite.innerHTML = "";
    const admin = ROLES_ADMIN.includes(role());
    for (const a of (rep.agents || [])) {
      const el = document.createElement("div");
      el.className = "carte-agent";
      el.innerHTML = `
        <div class="agent-txt">
          <strong></strong>
          <small>${a.optionnel ? "optionnel" : "indispensable"}</small>
        </div>
        <label class="bascule">
          <input type="checkbox" ${a.actif ? "checked" : ""} ${(!a.optionnel || !admin) ? "disabled" : ""}>
          <span class="glissiere"></span>
        </label>`;
      el.querySelector("strong").textContent = a.numero + ". " + a.nom;
      const cb = el.querySelector("input");
      cb.addEventListener("change", () => basculerAgent(a.numero, cb.checked));
      boite.appendChild(el);
    }
  } catch (e) { if (e.code !== 401) toast(e.message, "erreur"); }
}

async function basculerAgent(numero, actif) {
  try {
    await api("POST", "/agents/" + numero, { actif });
    toast("Agent " + numero + (actif ? " activé" : " désactivé"), "succes");
  } catch (e) { toast(e.message, "erreur"); chargerAgents(); }
}

// ── Mémoire & objectifs ─────────────────────────────────────────────────────
async function entrerMemoire() { afficherVue("memoire"); await chargerMemoire(); }

async function chargerMemoire() {
  try {
    const rep = await api("GET", "/memoire");
    const obj = rep.objectifs || {};
    const etat = rep.etat || {};
    $("#ch-objectifs").value = obj.texte || "";
    $("#objectifs-info").textContent = obj.modifie_le
      ? "Modifié le " + formaterDate(obj.modifie_le) + (obj.par ? " par " + obj.par : "")
      : "Aucun objectif enregistré.";

    const boite = $("#memoire-etat");
    boite.innerHTML = "";
    const cles = etat.cles || {};
    const noms = Object.keys(cles);
    if (!etat.present || noms.length === 0) {
      boite.innerHTML = `<p class="etat-vide">Aucune mémoire de travail enregistrée.</p>`;
    } else {
      for (const k of noms) {
        const l = document.createElement("div");
        l.className = "memoire-cle";
        l.innerHTML = `<strong></strong><span></span>`;
        l.querySelector("strong").textContent = k;
        l.querySelector("span").textContent = cles[k];
        boite.appendChild(l);
      }
    }
    const peutPiloter = ROLES_PILOTAGE.includes(role());
    $("#ch-objectifs").disabled = !peutPiloter;
    $("#btn-objectifs-enreg").hidden = !peutPiloter;
    $("#btn-memoire-reset").hidden = !ROLES_ADMIN.includes(role());
  } catch (e) { if (e.code !== 401) toast(e.message, "erreur"); }
}

async function enregistrerObjectifs() {
  try {
    await api("POST", "/objectifs", { texte: $("#ch-objectifs").value });
    toast("Objectifs enregistrés", "succes");
    chargerMemoire();
  } catch (e) { toast(e.message, "erreur"); }
}

async function reinitialiserMemoire() {
  if (!confirm("Réinitialiser la mémoire de travail (world_state) ?")) return;
  try {
    const rep = await api("POST", "/memoire/reset");
    toast(rep.message || "Mémoire réinitialisée", "succes");
    chargerMemoire();
  } catch (e) { toast(e.message, "erreur"); }
}

// ── Chat interactif avec un agent ───────────────────────────────────────────
async function entrerChat() { afficherVue("chat"); await remplirAgentsChat(); }

async function remplirAgentsChat() {
  const select = $("#ch-chat-agent");
  if (select.options.length > 0) return; // déjà rempli
  try {
    const rep = await api("GET", "/agents");
    for (const a of (rep.agents || [])) {
      const opt = document.createElement("option");
      opt.value = a.numero;
      opt.textContent = a.numero + ". " + a.nom;
      select.appendChild(opt);
    }
  } catch (e) { if (e.code !== 401) toast(e.message, "erreur"); }
}

function ajouterBulle(texte, cote) {
  const b = document.createElement("div");
  b.className = "bulle " + cote;
  b.textContent = texte;
  const fil = $("#chat-fil");
  fil.appendChild(b);
  fil.scrollTop = fil.scrollHeight;
  return b;
}

async function envoyerChat(evt) {
  evt.preventDefault();
  const champ = $("#ch-chat-msg");
  const message = champ.value.trim();
  if (!message) return;
  const numero = Number($("#ch-chat-agent").value);
  ajouterBulle(message, "moi");
  champ.value = "";
  const attente = ajouterBulle("…", "agent");
  try {
    const rep = await api("POST", "/chat", { agent: numero, message });
    attente.textContent = rep.reponse || "(pas de réponse)";
  } catch (e) {
    attente.textContent = "⚠️ " + e.message;
    attente.classList.add("erreur");
  }
}

// ── Nouvelle production (modale) ─────────────────────────────────────────────
function ouvrirModale() { $("#modale").hidden = false; $("#ch-idee").focus(); }
function fermerModale() { $("#modale").hidden = true; $("#form-production").reset(); }

async function lancerProduction(evt) {
  evt.preventDefault();
  const idee = $("#ch-idee").value.trim();
  if (!idee) return;
  const modele = $("#ch-modele").value.trim();
  try {
    const corps = { idee };
    if (modele) corps.modele = modele;
    const rep = await api("POST", "/productions", corps);
    fermerModale();
    toast("Production lancée : " + (rep.id || ""), "succes");
    rafraichirListe();
  } catch (e) {
    toast(e.message, "erreur");
  }
}

// ── Utilitaires d'affichage ─────────────────────────────────────────────────
function classeStatut(s) { return (s || "").toLowerCase().replace(/[^a-z_]/g, ""); }
function libelleStatut(s) {
  const m = { en_cours: "en cours", terminee: "terminée", echec: "échec",
              arretee: "arrêtée", reussie: "réussie", echouee: "échouée",
              ignoree: "ignorée" };
  return m[(s || "").toLowerCase()] || (s || "—");
}
function formaterDuree(sec) {
  if (sec == null) return "";
  if (sec < 60) return sec.toFixed(1) + " s";
  const m = Math.floor(sec / 60), r = Math.round(sec % 60);
  return m + " min " + (r < 10 ? "0" : "") + r + " s";
}
function formaterDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}
function formaterHeure(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleTimeString("fr-FR", { timeStyle: "medium" });
}
function echapper(t) {
  const div = document.createElement("div");
  div.textContent = t == null ? "" : String(t);
  return div.innerHTML;
}
function toast(message, type) {
  const t = $("#toast");
  t.textContent = message;
  t.className = "toast" + (type ? " " + type : "");
  t.hidden = false;
  clearTimeout(t._minuteur);
  t._minuteur = setTimeout(() => (t.hidden = true), 3200);
}

// ── Démarrage ────────────────────────────────────────────────────────────
function init() {
  $("#form-connexion").addEventListener("submit", seConnecter);
  $("#btn-deconnexion").addEventListener("click", seDeconnecter);
  $("#btn-rafraichir").addEventListener("click", rafraichirListe);
  $("#btn-nouvelle").addEventListener("click", ouvrirModale);
  $("#btn-annuler").addEventListener("click", fermerModale);
  $("#form-production").addEventListener("submit", lancerProduction);
  $("#btn-retour").addEventListener("click", entrerTableau);
  $("#btn-rafraichir-detail").addEventListener("click", () => afficherDetail(productionCourante, true));
  $("#modale").addEventListener("click", (e) => { if (e.target.id === "modale") fermerModale(); });

  // Navigation vers les vues Agents / Mémoire / Chat, et retours.
  $("#btn-nav-agents").addEventListener("click", entrerAgents);
  $("#btn-nav-memoire").addEventListener("click", entrerMemoire);
  $("#btn-nav-chat").addEventListener("click", entrerChat);
  document.querySelectorAll(".btn-retour-nav").forEach((b) =>
    b.addEventListener("click", entrerTableau));
  $("#btn-objectifs-enreg").addEventListener("click", enregistrerObjectifs);
  $("#btn-memoire-reset").addEventListener("click", reinitialiserMemoire);
  $("#form-chat").addEventListener("submit", envoyerChat);

  if (jeton()) entrerTableau();
  else afficherVue("connexion");

  // Service worker : utile en PWA web, mais source de problèmes en APK Capacitor
  // (fichiers locaux, origine non standard). On ne l'enregistre que sur le web.
  if (!EST_NATIF && "serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  }
}

document.addEventListener("DOMContentLoaded", init);
