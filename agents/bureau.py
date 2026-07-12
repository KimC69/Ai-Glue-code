"""
bureau.py — Application de BUREAU du Studio IA (étape 10 de la feuille de route).

Interface graphique pour Windows et Linux qui parle à l'API (api_serveur.py)
via la brique commune client_api.py. Elle permet, depuis un poste :

  - de se CONNECTER (nom + mot de passe → jeton de session) ;
  - de VOIR le tableau de bord des productions (liste + rafraîchissement) ;
  - de LANCER une nouvelle production (si le rôle le permet) ;
  - de SUIVRE en direct le détail d'une production : ses étapes ET le journal
    des événements de l'orchestrateur (son « raisonnement » et ses décisions).

Choix technique : Tkinter, qui fait partie de la bibliothèque standard de
Python — donc RIEN à installer sur la machine de l'utilisateur (fidèle à la
philosophie « zéro dépendance » du projet). Toute la communication réseau passe
par client_api.py, déjà testé : ce fichier ne contient que de l'affichage.

Note : Tkinter a besoin d'un environnement graphique (un écran). Il n'est donc
pas exécutable dans l'environnement d'intégration sans affichage — l'import est
protégé pour que le module reste importable (et sa logique testable) partout.

Lancement :  python bureau.py --url http://127.0.0.1:8000
"""

import argparse
import sys
import threading

from client_api import ClientAPI, ErreurAPI

try:                                    # Tkinter exige un affichage graphique.
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext
    TK_DISPONIBLE = True
except ImportError:                     # Sans écran : module importable quand même.
    TK_DISPONIBLE = False

ROLES_LANCEMENT = ("admin", "operateur")   # rôles ayant « lancer_production »
ROLES_PILOTAGE = ("admin", "operateur")    # rôles ayant « piloter_production »
ROLES_ADMIN = ("admin",)                     # rôles ayant « gerer_utilisateurs »
INTERVALLE_RAFRAICHISSEMENT_MS = 5000       # suivi en direct


# ── Helpers d'affichage (purs, donc testables sans Tkinter) ──────────────────

def libelle_statut(statut: str) -> str:
    """Traduit un code de statut en libellé lisible."""
    correspondances = {
        "en_cours": "en cours", "terminee": "terminée", "echec": "échec",
        "arretee": "arrêtée", "reussie": "réussie", "echouee": "échouée",
        "ignoree": "ignorée",
    }
    return correspondances.get((statut or "").lower(), statut or "—")


def formater_duree(secondes) -> str:
    """Durée lisible : « 4.2 s » en dessous d'une minute, « 2 min 05 s » au-delà."""
    if secondes is None:
        return ""
    if secondes < 60:
        return f"{secondes:.1f} s"
    minutes = int(secondes // 60)
    reste = int(round(secondes % 60))
    return f"{minutes} min {reste:02d} s"


def resumer_production(p: dict) -> str:
    """Ligne compacte pour la liste : idée (tronquée), statut, nb d'étapes."""
    idee = (p.get("idee") or "(sans titre)").replace("\n", " ")
    if len(idee) > 60:
        idee = idee[:57] + "…"
    statut = libelle_statut(p.get("statut", ""))
    reussies = p.get("etapes_reussies", 0)
    return f"[{statut}]  {idee}   · {reussies} étape(s)"


# ── Application graphique ────────────────────────────────────────────────────

class AppBureau:
    """Fenêtre principale. Trois écrans successifs gérés par masquage de cadres :
    connexion, tableau de bord, détail. La logique réseau est déléguée à
    ClientAPI et exécutée dans un thread pour ne jamais figer l'interface."""

    def __init__(self, racine, url: str):
        self.racine = racine
        self.client = ClientAPI(base_url=url)
        self.production_courante = None
        self.tache_rafraichissement = None

        racine.title("Studio IA — Bureau")
        racine.geometry("960x640")
        racine.minsize(760, 520)

        self.cadre_connexion = self._construire_connexion()
        self.cadre_tableau = self._construire_tableau()
        self._afficher(self.cadre_connexion)

    # -- utilitaires généraux --

    def _afficher(self, cadre):
        for c in (self.cadre_connexion, self.cadre_tableau):
            c.pack_forget()
        cadre.pack(fill="both", expand=True)

    def _en_arriere_plan(self, travail, sur_succes, sur_erreur=None):
        """Exécute `travail()` (un appel réseau) dans un thread, puis renvoie le
        résultat au thread graphique via `racine.after` — Tkinter n'est pas
        thread-safe, on ne touche à l'UI que depuis le thread principal."""
        def executer():
            try:
                resultat = travail()
            except ErreurAPI as e:
                self.racine.after(0, lambda: (sur_erreur or self._erreur_defaut)(e))
                return
            self.racine.after(0, lambda: sur_succes(resultat))
        threading.Thread(target=executer, daemon=True).start()

    def _erreur_defaut(self, e: ErreurAPI):
        if e.code == 401:                       # jeton expiré/révoqué → reconnexion
            self._deconnexion_locale()
            messagebox.showwarning("Session expirée",
                                   "Votre session a expiré. Reconnectez-vous.")
            self._afficher(self.cadre_connexion)
        else:
            messagebox.showerror("Erreur", e.message)

    # -- écran connexion --

    def _construire_connexion(self):
        cadre = ttk.Frame(self.racine, padding=40)
        centre = ttk.Frame(cadre)
        centre.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(centre, text="🎬  Studio IA", font=("", 22, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 4))
        ttk.Label(centre, text="Connexion à la régie").grid(
            row=1, column=0, columnspan=2, pady=(0, 20))

        ttk.Label(centre, text="Adresse de l'API").grid(row=2, column=0, sticky="w")
        self.ch_url = ttk.Entry(centre, width=34)
        self.ch_url.insert(0, self.client.base_url)
        self.ch_url.grid(row=2, column=1, pady=4)

        ttk.Label(centre, text="Nom d'utilisateur").grid(row=3, column=0, sticky="w")
        self.ch_nom = ttk.Entry(centre, width=34)
        self.ch_nom.grid(row=3, column=1, pady=4)

        ttk.Label(centre, text="Mot de passe").grid(row=4, column=0, sticky="w")
        self.ch_mdp = ttk.Entry(centre, width=34, show="•")
        self.ch_mdp.grid(row=4, column=1, pady=4)
        self.ch_mdp.bind("<Return>", lambda e: self._connexion())

        self.btn_connexion = ttk.Button(centre, text="Se connecter",
                                        command=self._connexion)
        self.btn_connexion.grid(row=5, column=0, columnspan=2, pady=(18, 0), sticky="ew")
        return cadre

    def _connexion(self):
        nom = self.ch_nom.get().strip()
        mdp = self.ch_mdp.get()
        if not nom or not mdp:
            messagebox.showwarning("Champs requis", "Renseignez le nom et le mot de passe.")
            return
        self.client.base_url = self.ch_url.get().strip().rstrip("/")
        self.btn_connexion.config(state="disabled", text="Connexion…")

        def apres(_):
            self.ch_mdp.delete(0, "end")
            self.btn_connexion.config(state="normal", text="Se connecter")
            self._entrer_tableau()

        def echec(e):
            self.btn_connexion.config(state="normal", text="Se connecter")
            messagebox.showerror("Connexion refusée", e.message)

        self._en_arriere_plan(
            lambda: self.client.connexion(nom, mdp), apres, echec)

    def _deconnexion_locale(self):
        if self.tache_rafraichissement:
            self.racine.after_cancel(self.tache_rafraichissement)
            self.tache_rafraichissement = None
        self.client.jeton = ""
        self.client.role = ""

    def _deconnexion(self):
        self._en_arriere_plan(self.client.deconnexion, lambda _: None,
                              lambda e: None)
        self._deconnexion_locale()
        self._afficher(self.cadre_connexion)

    # -- écran tableau de bord --

    def _construire_tableau(self):
        cadre = ttk.Frame(self.racine)

        barre = ttk.Frame(cadre, padding=(12, 10))
        barre.pack(fill="x")
        self.lbl_titre = ttk.Label(barre, text="Studio IA", font=("", 14, "bold"))
        self.lbl_titre.pack(side="left")
        self.lbl_role = ttk.Label(barre, text="", foreground="#b98800")
        self.lbl_role.pack(side="left", padx=10)

        ttk.Button(barre, text="Se déconnecter", command=self._deconnexion).pack(side="right")
        ttk.Button(barre, text="↻ Rafraîchir", command=self._rafraichir_liste).pack(side="right", padx=6)
        self.btn_nouvelle = ttk.Button(barre, text="+ Nouvelle production",
                                       command=self._dialogue_nouvelle)
        self.btn_nouvelle.pack(side="right", padx=6)
        self.btn_chat = ttk.Button(barre, text="💬 Chat", command=self._dialogue_chat)
        self.btn_chat.pack(side="right", padx=6)
        self.btn_memoire = ttk.Button(barre, text="🧠 Mémoire", command=self._dialogue_memoire)
        self.btn_memoire.pack(side="right", padx=6)
        self.btn_agents = ttk.Button(barre, text="🎭 Agents", command=self._dialogue_agents)
        self.btn_agents.pack(side="right", padx=6)

        panneaux = ttk.Panedwindow(cadre, orient="horizontal")
        panneaux.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Gauche : liste des productions
        gauche = ttk.Frame(panneaux)
        ttk.Label(gauche, text="Productions", font=("", 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.liste = tk.Listbox(gauche, activestyle="none")
        self.liste.pack(fill="both", expand=True)
        self.liste.bind("<<ListboxSelect>>", self._selection_production)
        self._productions = []
        panneaux.add(gauche, weight=1)

        # Droite : détail
        droite = ttk.Frame(panneaux)
        self.lbl_detail_titre = ttk.Label(droite, text="Sélectionnez une production",
                                          font=("", 12, "bold"), wraplength=460, justify="left")
        self.lbl_detail_titre.pack(anchor="w", pady=(0, 4))
        self.lbl_detail_meta = ttk.Label(droite, text="", foreground="#555")
        self.lbl_detail_meta.pack(anchor="w", pady=(0, 10))

        # Boutons de pilotage à distance (activés seulement si la production est
        # en cours / en pause et si le rôle a la permission « piloter_production »).
        self.cadre_controle = ttk.Frame(droite)
        self.cadre_controle.pack(anchor="w", pady=(0, 10))
        self.btn_pause = ttk.Button(self.cadre_controle, text="⏸️ Pause",
                                    state="disabled", command=lambda: self._piloter("pause"))
        self.btn_pause.pack(side="left", padx=(0, 6))
        self.btn_reprendre = ttk.Button(self.cadre_controle, text="▶️ Reprendre",
                                        state="disabled", command=lambda: self._piloter("reprendre"))
        self.btn_reprendre.pack(side="left", padx=6)
        self.btn_arreter = ttk.Button(self.cadre_controle, text="⏹️ Arrêter",
                                      state="disabled", command=lambda: self._piloter("arreter"))
        self.btn_arreter.pack(side="left", padx=6)

        ttk.Label(droite, text="Étapes").pack(anchor="w")
        self.tableau_etapes = ttk.Treeview(
            droite, columns=("num", "nom", "statut", "duree"), show="headings", height=8)
        for col, titre, larg in (("num", "#", 40), ("nom", "Étape", 240),
                                 ("statut", "Statut", 90), ("duree", "Durée", 90)):
            self.tableau_etapes.heading(col, text=titre)
            self.tableau_etapes.column(col, width=larg, anchor="w")
        self.tableau_etapes.pack(fill="x", pady=(2, 10))

        ttk.Label(droite, text="Journal / raisonnement de l'orchestrateur").pack(anchor="w")
        self.zone_journal = scrolledtext.ScrolledText(droite, height=10, wrap="word",
                                                      state="disabled")
        self.zone_journal.pack(fill="both", expand=True, pady=(2, 0))
        panneaux.add(droite, weight=2)
        return cadre

    def _entrer_tableau(self):
        self.lbl_role.config(text=f"rôle : {self.client.role}")
        peut_lancer = self.client.role in ROLES_LANCEMENT
        self.btn_nouvelle.config(state="normal" if peut_lancer else "disabled")
        # Le chat exige « piloter_production » : sinon on désactive le bouton.
        self.btn_chat.config(
            state="normal" if self.client.role in ROLES_PILOTAGE else "disabled")
        self._afficher(self.cadre_tableau)
        self._rafraichir_liste()
        self._programmer_rafraichissement()

    def _programmer_rafraichissement(self):
        # Rafraîchissement périodique tant qu'on est connecté (suivi en direct).
        if not self.client.connecte:
            return
        self.tache_rafraichissement = self.racine.after(
            INTERVALLE_RAFRAICHISSEMENT_MS, self._rafraichissement_auto)

    def _rafraichissement_auto(self):
        self._rafraichir_liste()
        if self.production_courante:
            self._charger_detail(self.production_courante)
        self._programmer_rafraichissement()

    def _rafraichir_liste(self):
        self._en_arriere_plan(self.client.lister_productions, self._afficher_liste)

    def _afficher_liste(self, productions):
        selection = self.liste.curselection()
        index_selectionne = selection[0] if selection else None
        self._productions = productions
        self.liste.delete(0, "end")
        for p in productions:
            self.liste.insert("end", resumer_production(p))
        if index_selectionne is not None and index_selectionne < len(productions):
            self.liste.selection_set(index_selectionne)

    def _selection_production(self, _evt):
        selection = self.liste.curselection()
        if not selection:
            return
        p = self._productions[selection[0]]
        self.production_courante = p.get("id")
        self._charger_detail(self.production_courante)

    def _charger_detail(self, production_id):
        self._en_arriere_plan(
            lambda: self.client.details_production(production_id),
            self._afficher_detail)

    def _afficher_detail(self, details):
        p = details.get("production", {})
        self.lbl_detail_titre.config(text=p.get("idee", "(sans titre)"))
        meta = (f"Statut : {libelle_statut(p.get('statut',''))}   ·   "
                f"Modèle : {p.get('modele') or 'défaut'}   ·   "
                f"Démarrée : {p.get('demarree_le', '—')}")
        if p.get("terminee_le"):
            meta += f"   ·   Terminée : {p['terminee_le']}"
        self.lbl_detail_meta.config(text=meta)

        # État des boutons de pilotage selon le statut courant et le rôle.
        statut = p.get("statut", "")
        pilotable = (statut in ("en_cours", "en_pause")
                     and self.client.role in ROLES_PILOTAGE)
        self.btn_arreter.config(state="normal" if pilotable else "disabled")
        self.btn_pause.config(
            state="normal" if pilotable and statut == "en_cours" else "disabled")
        self.btn_reprendre.config(
            state="normal" if pilotable and statut == "en_pause" else "disabled")

        for ligne in self.tableau_etapes.get_children():
            self.tableau_etapes.delete(ligne)
        for e in details.get("etapes", []):
            self.tableau_etapes.insert("", "end", values=(
                e.get("numero", ""), e.get("nom", ""),
                libelle_statut(e.get("statut", "")), formater_duree(e.get("duree_s"))))

        self.zone_journal.config(state="normal")
        self.zone_journal.delete("1.0", "end")
        for ev in details.get("evenements", []):
            heure = ev.get("horodatage", "")
            self.zone_journal.insert("end",
                f"{heure}  [{ev.get('type','')}]  {ev.get('message','')}\n")
        self.zone_journal.config(state="disabled")

    # -- dialogue nouvelle production --

    def _dialogue_nouvelle(self):
        fenetre = tk.Toplevel(self.racine)
        fenetre.title("Nouvelle production")
        fenetre.geometry("480x300")
        fenetre.transient(self.racine)
        fenetre.grab_set()

        ttk.Label(fenetre, text="Idée du film", padding=(12, 12, 12, 4)).pack(anchor="w")
        champ_idee = scrolledtext.ScrolledText(fenetre, height=6, wrap="word")
        champ_idee.pack(fill="both", expand=True, padx=12)

        ligne = ttk.Frame(fenetre, padding=12)
        ligne.pack(fill="x")
        ttk.Label(ligne, text="Modèle (optionnel)").pack(side="left")
        champ_modele = ttk.Entry(ligne)
        champ_modele.pack(side="left", fill="x", expand=True, padx=8)

        actions = ttk.Frame(fenetre, padding=(12, 0, 12, 12))
        actions.pack(fill="x")

        def lancer():
            idee = champ_idee.get("1.0", "end").strip()
            if not idee:
                messagebox.showwarning("Idée requise", "Décrivez l'idée du film.", parent=fenetre)
                return
            modele = champ_modele.get().strip()

            def apres(rep):
                fenetre.destroy()
                messagebox.showinfo("Lancée", f"Production lancée : {rep.get('id','')}")
                self._rafraichir_liste()

            self._en_arriere_plan(
                lambda: self.client.lancer_production(idee, modele), apres)

        ttk.Button(actions, text="Annuler", command=fenetre.destroy).pack(side="right")
        ttk.Button(actions, text="Lancer", command=lancer).pack(side="right", padx=8)

    # -- pilotage à distance (pause / reprise / arrêt) --

    def _piloter(self, commande):
        pid = self.production_courante
        if not pid:
            return
        if commande == "arreter" and not messagebox.askyesno(
                "Arrêter", "Arrêter définitivement cette production ?"):
            return

        def apres(rep):
            messagebox.showinfo("Pilotage", rep.get("message", "Commande transmise."))
            self._charger_detail(pid)

        self._en_arriere_plan(
            lambda: self.client.piloter_production(pid, commande), apres)

    # -- dialogue « agents » (activation / désactivation) --

    def _dialogue_agents(self):
        fenetre = tk.Toplevel(self.racine)
        fenetre.title("Agents du pipeline")
        fenetre.geometry("540x460")
        fenetre.transient(self.racine)
        ttk.Label(fenetre, wraplength=500, justify="left", padding=12,
                  text="Activez ou désactivez les agents optionnels. La chaîne "
                       "créative (agents 1 à 5) est indispensable et ne peut pas "
                       "être désactivée. (Réglage réservé aux administrateurs.)"
                  ).pack(anchor="w")
        conteneur = ttk.Frame(fenetre, padding=(12, 0))
        conteneur.pack(fill="both", expand=True)
        admin = self.client.role in ROLES_ADMIN

        def recharger():
            self._en_arriere_plan(self.client.lister_agents, rendre)

        def rendre(agents):
            for w in conteneur.winfo_children():
                w.destroy()
            for a in agents:
                ligne = ttk.Frame(conteneur)
                ligne.pack(fill="x", pady=3)
                var = tk.BooleanVar(value=a.get("actif", True))
                etat = "normal" if (a.get("optionnel") and admin) else "disabled"
                ttk.Checkbutton(
                    ligne, variable=var, state=etat,
                    command=lambda n=a["numero"], v=var: self._basculer_agent(
                        n, v.get(), recharger)).pack(side="left")
                genre = "optionnel" if a.get("optionnel") else "indispensable"
                ttk.Label(ligne, text=f"{a['numero']}. {a['nom']}  ({genre})"
                          ).pack(side="left", padx=6)

        recharger()

    def _basculer_agent(self, numero, actif, recharger):
        def echec(e):
            messagebox.showerror("Erreur", e.message)
            recharger()   # remet la case dans son état réel côté serveur
        self._en_arriere_plan(
            lambda: self.client.definir_agent(numero, actif),
            lambda _: None, echec)

    # -- dialogue « mémoire & objectifs » --

    def _dialogue_memoire(self):
        fenetre = tk.Toplevel(self.racine)
        fenetre.title("Mémoire & objectifs")
        fenetre.geometry("580x560")
        fenetre.transient(self.racine)
        peut_piloter = self.client.role in ROLES_PILOTAGE

        ttk.Label(fenetre, padding=(12, 12, 12, 4),
                  text="Objectifs persistants (injectés au lancement des "
                       "nouvelles productions)").pack(anchor="w")
        champ = scrolledtext.ScrolledText(fenetre, height=6, wrap="word")
        champ.pack(fill="x", padx=12)
        info = ttk.Label(fenetre, text="", foreground="#888", padding=(12, 4))
        info.pack(anchor="w")

        ttk.Label(fenetre, padding=(12, 8, 12, 4),
                  text="État de travail (mémoire vive)").pack(anchor="w")
        zone = scrolledtext.ScrolledText(fenetre, height=10, wrap="word",
                                         state="disabled")
        zone.pack(fill="both", expand=True, padx=12)

        actions = ttk.Frame(fenetre, padding=12)
        actions.pack(fill="x")

        def charger(rep):
            obj = rep.get("objectifs", {})
            etat = rep.get("etat", {})
            champ.delete("1.0", "end")
            champ.insert("1.0", obj.get("texte", ""))
            info.config(text=(f"Modifié le {obj.get('modifie_le','')}"
                              + (f" par {obj['par']}" if obj.get("par") else ""))
                        if obj.get("modifie_le") else "Aucun objectif enregistré.")
            cles = etat.get("cles", {})
            zone.config(state="normal")
            zone.delete("1.0", "end")
            if not cles:
                zone.insert("end", "(aucune mémoire de travail enregistrée)")
            else:
                for cle, valeur in cles.items():
                    zone.insert("end", f"• {cle} : {valeur}\n\n")
            zone.config(state="disabled")

        def enregistrer():
            texte = champ.get("1.0", "end").strip()
            self._en_arriere_plan(
                lambda: self.client.definir_objectifs(texte),
                lambda _: messagebox.showinfo(
                    "Objectifs", "Objectifs enregistrés.", parent=fenetre))

        def reinitialiser():
            if not messagebox.askyesno(
                    "Réinitialiser", "Effacer la mémoire de travail ?",
                    parent=fenetre):
                return

            def apres(rep):
                messagebox.showinfo("Mémoire",
                                    rep.get("message", "Réinitialisée."),
                                    parent=fenetre)
                self._en_arriere_plan(self.client.lire_memoire, charger)

            self._en_arriere_plan(self.client.reinitialiser_memoire, apres)

        if peut_piloter:
            ttk.Button(actions, text="Enregistrer les objectifs",
                       command=enregistrer).pack(side="left")
        else:
            champ.config(state="disabled")
        if self.client.role in ROLES_ADMIN:
            ttk.Button(actions, text="Réinitialiser la mémoire",
                       command=reinitialiser).pack(side="right")

        self._en_arriere_plan(self.client.lire_memoire, charger)

    # -- dialogue « chat » --

    def _dialogue_chat(self):
        fenetre = tk.Toplevel(self.racine)
        fenetre.title("Discuter avec un agent")
        fenetre.geometry("620x560")
        fenetre.transient(self.racine)

        haut = ttk.Frame(fenetre, padding=12)
        haut.pack(fill="x")
        ttk.Label(haut, text="Agent :").pack(side="left")
        combo = ttk.Combobox(haut, state="readonly")
        combo.pack(side="left", fill="x", expand=True, padx=8)

        fil = scrolledtext.ScrolledText(fenetre, wrap="word", state="disabled")
        fil.pack(fill="both", expand=True, padx=12)

        bas = ttk.Frame(fenetre, padding=12)
        bas.pack(fill="x")
        champ = ttk.Entry(bas)
        champ.pack(side="left", fill="x", expand=True)
        btn = ttk.Button(bas, text="Envoyer")
        btn.pack(side="left", padx=8)

        agents_map = {}

        def remplir(agents):
            libelles = []
            for a in agents:
                libelle = f"{a['numero']}. {a['nom']}"
                agents_map[libelle] = a["numero"]
                libelles.append(libelle)
            combo["values"] = libelles
            if libelles:
                combo.current(0)

        def ajouter(texte):
            fil.config(state="normal")
            fil.insert("end", texte + "\n\n")
            fil.see("end")
            fil.config(state="disabled")

        def envoyer(_evt=None):
            message = champ.get().strip()
            libelle = combo.get()
            if not message or libelle not in agents_map:
                return
            numero = agents_map[libelle]
            ajouter("Vous : " + message)
            champ.delete(0, "end")
            btn.config(state="disabled")

            def apres(reponse):
                ajouter("Agent : " + (reponse or "(pas de réponse)"))
                btn.config(state="normal")

            def echec(e):
                ajouter("⚠️ " + e.message)
                btn.config(state="normal")

            self._en_arriere_plan(
                lambda: self.client.chat(numero, message), apres, echec)

        btn.config(command=envoyer)
        champ.bind("<Return>", envoyer)
        self._en_arriere_plan(self.client.lister_agents, remplir)


def principal(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Application de bureau du Studio IA (interface graphique Tkinter).")
    parser.add_argument("--url", default="http://127.0.0.1:8000",
                        help="Adresse de l'API (défaut : http://127.0.0.1:8000)")
    args = parser.parse_args(argv)

    if not TK_DISPONIBLE:
        print("[Erreur] : Tkinter est introuvable. Sous Linux, installez le "
              "paquet système « python3-tk » ; sous Windows/macOS, il est "
              "normalement inclus avec Python.")
        return 1

    try:
        racine = tk.Tk()
    except tk.TclError as e:
        print(f"[Erreur] : impossible d'ouvrir une fenêtre graphique ({e}). "
              "Un environnement de bureau (écran) est nécessaire.")
        return 1

    AppBureau(racine, url=args.url)
    racine.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
