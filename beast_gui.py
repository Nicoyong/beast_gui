"""
BEAST GUI v2 - lanceur BEAST avec file d'attente et pause/reprise automatiques (Windows).

Dépendance : psutil (installée automatiquement par lancer_beast_gui.bat)
"""
import ctypes
import json
import os
import queue
import shlex
import subprocess
import threading
import time
import tkinter as tk
import winsound
from ctypes import wintypes
from tkinter import filedialog, messagebox, ttk

import psutil

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beast_gui_settings.json")

DEFAULTS = {
    "bat": r"D:\Users\Nicolas\Desktop\BEAST\bat\beast.bat",
    "mode": "CPU",            # CPU / GPU / Aucun
    "threads": 10,
    "resume": False,          # BEAST -resume
    "overwrite": False,       # BEAST -overwrite
    "working": True,          # BEAST -working
    "extra": "",
    "auto_pause": True,
    "pause_delay": 10,        # secondes d'utilisation avant la pause
    "auto_resume": True,
    "resume_minutes": 15,     # minutes d'inactivité avant la reprise
    "keyboard": True,         # compter aussi le clavier
    "continue_on_error": True,
    "beep": True,             # bip à la fin de la file
    "queue": [],
}

STATUS_COLORS = {
    "en cours": "#0b5fff", "terminé": "#1a8a3a", "erreur": "#c62828",
    "ignoré": "#888888", "arrêté": "#b36b00", "attente": "#000000",
}


# ---------------------------------------------------------------- activité utilisateur (Windows)
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


ctypes.windll.kernel32.GetTickCount.restype = ctypes.c_uint32


def cursor_pos():
    p = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


def input_idle_seconds():
    """Temps depuis la dernière entrée clavier OU souris."""
    li = LASTINPUTINFO()
    li.cbSize = ctypes.sizeof(li)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
    return ((ctypes.windll.kernel32.GetTickCount() - li.dwTime) & 0xFFFFFFFF) / 1000.0


def fmt_mmss(seconds):
    seconds = int(max(0, seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# ---------------------------------------------------------------- application
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BEAST - lanceur")
        self.geometry("880x800")

        self.cfg = self.load_settings()
        self.items = [
            {"path": i["path"], "status": "terminé" if i.get("status") == "terminé" else "attente"}
            for i in self.cfg.get("queue", []) if isinstance(i, dict) and "path" in i
        ]

        self.proc = None
        self.current = None            # élément de la file en cours
        self.queue_running = False
        self.run_state = "arrêté"      # arrêté / en cours / en pause
        self.auto_paused = False
        self.q = queue.Queue()

        self.last_pos = cursor_pos()
        self.last_move = time.time()
        self.active_since = None

        self.build_ui()
        self.refresh_list()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(500, self.tick)

    # ------------------------------------------------ réglages
    def load_settings(self):
        cfg = dict(DEFAULTS)
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (OSError, ValueError):
            pass
        return cfg

    def save_settings(self):
        data = {}
        for k, var in self.vars.items():
            try:
                data[k] = var.get()
            except tk.TclError:
                data[k] = DEFAULTS[k]
        data["queue"] = [{"path": i["path"], "status": i["status"]} for i in self.items]
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    # ------------------------------------------------ interface
    def build_ui(self):
        c = self.cfg
        self.vars = {
            "bat": tk.StringVar(value=c["bat"]),
            "mode": tk.StringVar(value=c["mode"]),
            "threads": tk.IntVar(value=c["threads"]),
            "resume": tk.BooleanVar(value=c["resume"]),
            "overwrite": tk.BooleanVar(value=c["overwrite"]),
            "working": tk.BooleanVar(value=c["working"]),
            "extra": tk.StringVar(value=c["extra"]),
            "auto_pause": tk.BooleanVar(value=c["auto_pause"]),
            "pause_delay": tk.IntVar(value=c["pause_delay"]),
            "auto_resume": tk.BooleanVar(value=c["auto_resume"]),
            "resume_minutes": tk.IntVar(value=c["resume_minutes"]),
            "keyboard": tk.BooleanVar(value=c["keyboard"]),
            "continue_on_error": tk.BooleanVar(value=c["continue_on_error"]),
            "beep": tk.BooleanVar(value=c["beep"]),
        }
        v = self.vars

        # --- beast.bat
        f1 = ttk.LabelFrame(self, text="BEAST")
        f1.pack(fill="x", padx=8, pady=4)
        f1.columnconfigure(1, weight=1)
        ttk.Label(f1, text="beast.bat").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(f1, textvariable=v["bat"]).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(f1, text="...", width=4, command=self.pick_bat).grid(row=0, column=2, padx=4)

        # --- file d'attente
        fq = ttk.LabelFrame(self, text="File d'attente (traitée dans l'ordre)")
        fq.pack(fill="x", padx=8, pady=4)
        fq.columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(fq, height=7, selectmode="extended", exportselection=False,
                                  font=("Consolas", 9))
        sb = ttk.Scrollbar(fq, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.grid(row=0, column=0, sticky="ew", padx=(4, 0), pady=4)
        sb.grid(row=0, column=1, sticky="ns", pady=4)
        side = ttk.Frame(fq)
        side.grid(row=0, column=2, padx=4, sticky="n")
        for text, cmd in (("Ajouter...", self.add_files), ("Retirer", self.remove_selected),
                          ("Monter", lambda: self.move(-1)), ("Descendre", lambda: self.move(1)),
                          ("Tout vider", self.clear_all)):
            ttk.Button(side, text=text, command=cmd, width=12).pack(pady=1)
        ttk.Checkbutton(fq, text="Continuer avec le suivant si un fichier échoue",
                        variable=v["continue_on_error"]).grid(row=1, column=0, sticky="w", padx=4)
        ttk.Checkbutton(fq, text="Bip à la fin de la file", variable=v["beep"]).grid(
            row=1, column=2, sticky="w", padx=4)

        # --- paramètres BEAST
        f2 = ttk.LabelFrame(self, text="Paramètres BEAST (communs à tous les fichiers)")
        f2.pack(fill="x", padx=8, pady=4)
        ttk.Label(f2, text="Calcul").grid(row=0, column=0, padx=4, pady=2, sticky="w")
        ttk.Combobox(f2, textvariable=v["mode"], values=["CPU", "GPU", "Aucun"],
                     width=8, state="readonly").grid(row=0, column=1, padx=4)
        ttk.Label(f2, text="Threads (CPU)").grid(row=0, column=2, padx=4, sticky="w")
        ttk.Spinbox(f2, from_=1, to=64, textvariable=v["threads"], width=6).grid(row=0, column=3, padx=4)
        ttk.Checkbutton(f2, text="Reprendre le run (-resume)", variable=v["resume"]).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=4)
        ttk.Checkbutton(f2, text="Écraser les sorties (-overwrite)", variable=v["overwrite"]).grid(
            row=1, column=2, columnspan=2, sticky="w", padx=4)
        ttk.Checkbutton(f2, text="Dossier du XML (-working)", variable=v["working"]).grid(
            row=1, column=4, sticky="w", padx=4)
        ttk.Label(f2, text="Options en plus").grid(row=2, column=0, padx=4, pady=2, sticky="w")
        ttk.Entry(f2, textvariable=v["extra"]).grid(row=2, column=1, columnspan=4, sticky="ew", padx=4)
        f2.columnconfigure(4, weight=1)

        # --- pause / reprise automatique
        f3 = ttk.LabelFrame(self, text="Pause / reprise automatique")
        f3.pack(fill="x", padx=8, pady=4)
        ttk.Checkbutton(f3, text="Mettre en pause si j'utilise le PC pendant", variable=v["auto_pause"]).grid(
            row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Spinbox(f3, from_=0, to=3600, textvariable=v["pause_delay"], width=6).grid(row=0, column=1)
        ttk.Label(f3, text="secondes").grid(row=0, column=2, sticky="w", padx=4)
        ttk.Checkbutton(f3, text="Reprendre si le PC est inactif pendant", variable=v["auto_resume"]).grid(
            row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Spinbox(f3, from_=1, to=1440, textvariable=v["resume_minutes"], width=6).grid(row=1, column=1)
        ttk.Label(f3, text="minutes").grid(row=1, column=2, sticky="w", padx=4)
        ttk.Checkbutton(f3, text="Compter aussi le clavier (sinon souris seulement)",
                        variable=v["keyboard"]).grid(row=2, column=0, columnspan=3, sticky="w", padx=4)
        self.idle_lbl = ttk.Label(f3, text="")
        self.idle_lbl.grid(row=3, column=0, columnspan=4, sticky="w", padx=4, pady=2)

        # --- boutons
        f4 = ttk.Frame(self)
        f4.pack(fill="x", padx=8, pady=4)
        self.btn_start = ttk.Button(f4, text="Lancer la file", command=self.start_queue)
        self.btn_pause = ttk.Button(f4, text="Pause", command=lambda: self.pause(auto=False))
        self.btn_resume = ttk.Button(f4, text="Reprendre", command=lambda: self.resume_calc(auto=False))
        self.btn_skip = ttk.Button(f4, text="Ignorer ce fichier", command=self.skip)
        self.btn_stop = ttk.Button(f4, text="Tout arrêter", command=self.stop)
        for b in (self.btn_start, self.btn_pause, self.btn_resume, self.btn_skip, self.btn_stop):
            b.pack(side="left", padx=3)
        self.status = ttk.Label(f4, text="État : arrêté", font=("Segoe UI", 10, "bold"))
        self.status.pack(side="right", padx=8)

        # --- journal
        f5 = ttk.LabelFrame(self, text="Sortie de BEAST")
        f5.pack(fill="both", expand=True, padx=8, pady=4)
        self.log = tk.Text(f5, height=10, wrap="none", state="disabled", font=("Consolas", 9))
        sb2 = ttk.Scrollbar(f5, command=self.log.yview)
        self.log.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)
        self.update_buttons()

    def pick_bat(self):
        p = filedialog.askopenfilename(title="beast.bat", filetypes=[("Batch", "*.bat"), ("Tous", "*.*")])
        if p:
            self.vars["bat"].set(os.path.normpath(p))

    # ------------------------------------------------ file d'attente
    def refresh_list(self):
        sel = self.listbox.curselection()
        self.listbox.delete(0, "end")
        for i, it in enumerate(self.items):
            name = os.path.basename(it["path"])
            self.listbox.insert("end", f"[{it['status']:<8}] {name}    {os.path.dirname(it['path'])}")
            self.listbox.itemconfig(i, fg=STATUS_COLORS.get(it["status"], "#000000"))
        for i in sel:
            if i < len(self.items):
                self.listbox.selection_set(i)

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Fichiers XML", filetypes=[("XML", "*.xml"), ("Tous", "*.*")])
        for p in paths:
            self.items.append({"path": os.path.normpath(p), "status": "attente"})
        self.refresh_list()
        self.save_settings()

    def remove_selected(self):
        for i in reversed(self.listbox.curselection()):
            if self.items[i]["status"] != "en cours":
                del self.items[i]
        self.refresh_list()
        self.save_settings()

    def move(self, delta):
        sel = self.listbox.curselection()
        if not sel:
            return
        i, j = sel[0], sel[0] + delta
        if 0 <= j < len(self.items):
            self.items[i], self.items[j] = self.items[j], self.items[i]
            self.refresh_list()
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(j)
            self.save_settings()

    def clear_all(self):
        if self.queue_running:
            messagebox.showinfo("File d'attente", "Arrête la file avant de la vider.")
            return
        self.items.clear()
        self.refresh_list()
        self.save_settings()

    # ------------------------------------------------ affichage
    def write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        if int(self.log.index("end-1c").split(".")[0]) > 3000:
            self.log.delete("1.0", "500.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_state(self, state, extra=""):
        self.run_state = state
        self.status.configure(text=f"État : {state}{extra}")
        self.update_buttons()

    def update_buttons(self):
        s = self.run_state
        self.btn_start.state(["!disabled"] if s == "arrêté" else ["disabled"])
        self.btn_pause.state(["!disabled"] if s == "en cours" else ["disabled"])
        self.btn_resume.state(["!disabled"] if s == "en pause" else ["disabled"])
        self.btn_skip.state(["!disabled"] if s != "arrêté" else ["disabled"])
        self.btn_stop.state(["!disabled"] if s != "arrêté" else ["disabled"])

    # ------------------------------------------------ gestion de la file et du processus
    def build_command(self, xml_path):
        v = {k: x.get() for k, x in self.vars.items()}
        cmd = [v["bat"]]
        if v["mode"] == "CPU":
            cmd.append("-beagle_CPU")
        elif v["mode"] == "GPU":
            cmd.append("-beagle_GPU")
        if v["mode"] != "GPU":
            cmd += ["-threads", str(v["threads"])]
        if v["resume"]:
            cmd.append("-resume")
        if v["overwrite"]:
            cmd.append("-overwrite")
        if v["working"]:
            cmd.append("-working")
        if v["extra"].strip():
            cmd += shlex.split(v["extra"], posix=False)
        cmd.append(xml_path)
        return cmd, os.path.dirname(xml_path)

    def start_queue(self):
        if self.run_state != "arrêté":
            return
        if not os.path.isfile(self.vars["bat"].get()):
            messagebox.showerror("Erreur", "beast.bat introuvable.")
            return
        if not self.items:
            messagebox.showinfo("File d'attente", "Ajoute d'abord au moins un fichier XML.")
            return
        for it in self.items:
            if it["status"] in ("erreur", "ignoré", "arrêté"):
                it["status"] = "attente"
        if not any(it["status"] == "attente" for it in self.items):
            if not messagebox.askyesno("File d'attente", "Tout est terminé. Tout relancer ?"):
                return
            for it in self.items:
                it["status"] = "attente"
        self.save_settings()
        self.queue_running = True
        self.run_next()

    def run_next(self):
        nxt = next((it for it in self.items if it["status"] == "attente"), None)
        if nxt is None:
            self.queue_running = False
            self.current = None
            self.write_log("\n[File d'attente terminée]\n")
            self.set_state("arrêté")
            self.refresh_list()
            if self.vars["beep"].get():
                winsound.MessageBeep()
            return
        if not os.path.isfile(nxt["path"]):
            nxt["status"] = "erreur"
            self.write_log(f"\n[Fichier introuvable : {nxt['path']}]\n")
            self.run_next()
            return
        cmd, cwd = self.build_command(nxt["path"])
        self.write_log("\n> " + subprocess.list2cmdline(cmd) + "\n")
        try:
            proc = subprocess.Popen(
                cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError as e:
            nxt["status"] = "erreur"
            self.queue_running = False
            self.set_state("arrêté")
            self.refresh_list()
            messagebox.showerror("Erreur", f"Impossible de lancer BEAST :\n{e}")
            return
        self.proc = proc
        self.current = nxt
        nxt["status"] = "en cours"
        self.auto_paused = False
        self.active_since = None
        threading.Thread(target=self.reader, args=(proc,), daemon=True).start()
        self.set_state("en cours")
        self.refresh_list()

    def reader(self, proc):
        for line in proc.stdout:
            self.q.put(("line", line))
        code = proc.wait()
        self.q.put(("end", proc, code))

    @staticmethod
    def tree(proc):
        try:
            root = psutil.Process(proc.pid)
            return [root] + root.children(recursive=True)
        except psutil.Error:
            return []

    def kill_tree(self, proc):
        for p in reversed(self.tree(proc)):
            try:
                p.kill()
            except psutil.Error:
                pass

    def pause(self, auto=False):
        if self.run_state != "en cours" or self.proc is None:
            return
        for p in self.tree(self.proc):
            try:
                p.suspend()
            except psutil.Error:
                pass
        self.auto_paused = auto
        self.set_state("en pause", " (auto)" if auto else "")

    def resume_calc(self, auto=False):
        if self.run_state != "en pause" or self.proc is None:
            return
        for p in self.tree(self.proc):
            try:
                p.resume()
            except psutil.Error:
                pass
        self.auto_paused = False
        self.active_since = None
        self.set_state("en cours")

    def skip(self):
        """Abandonne le fichier en cours et passe au suivant."""
        if self.proc is None:
            return
        proc, item = self.proc, self.current
        self.proc = None
        self.kill_tree(proc)
        item["status"] = "ignoré"
        self.write_log("\n[Fichier ignoré par l'utilisateur]\n")
        self.run_next()

    def stop(self):
        proc, item = self.proc, self.current
        self.proc = None
        self.queue_running = False
        if proc is not None:
            self.kill_tree(proc)
            if item is not None:
                item["status"] = "arrêté"
            self.write_log("\n[Tout arrêté par l'utilisateur]\n")
        self.current = None
        self.set_state("arrêté")
        self.refresh_list()

    # ------------------------------------------------ boucle principale (500 ms)
    def tick(self):
        # sortie de BEAST et fin de processus
        for _ in range(300):
            try:
                msg = self.q.get_nowait()
            except queue.Empty:
                break
            if msg[0] == "line":
                self.write_log(msg[1])
                continue
            _, proc, code = msg
            if proc is not self.proc:
                continue            # processus déjà arrêté ou ignoré
            self.proc = None
            item = self.current
            self.write_log(f"\n[BEAST terminé, code {code}]\n")
            if item is not None:
                item["status"] = "terminé" if code == 0 else "erreur"
            self.auto_paused = False
            self.save_settings()
            if self.queue_running and (code == 0 or self.vars["continue_on_error"].get()):
                self.run_next()
            else:
                self.queue_running = False
                self.current = None
                self.set_state("arrêté")
                self.refresh_list()

        # activité utilisateur
        now = time.time()
        pos = cursor_pos()
        if pos != self.last_pos:
            self.last_pos = pos
            self.last_move = now
        idle = now - self.last_move
        try:
            if self.vars["keyboard"].get():
                idle = min(idle, input_idle_seconds())
        except tk.TclError:
            pass

        # une période d'activité commence au 1er mouvement ; un trou de plus de 3 s la remet à zéro
        if idle < 1.5:
            if self.active_since is None:
                self.active_since = now
        elif idle > 3:
            self.active_since = None

        info = f"Inactivité du PC : {fmt_mmss(idle)}"
        try:
            if self.run_state == "en cours" and self.vars["auto_pause"].get():
                delay = self.vars["pause_delay"].get()
                if self.active_since is not None:
                    elapsed = now - self.active_since
                    if elapsed >= delay:
                        self.pause(auto=True)
                    else:
                        info += f"   |   pause dans {int(delay - elapsed) + 1} s si tu continues"
            elif self.run_state == "en pause" and self.auto_paused and self.vars["auto_resume"].get():
                wait = self.vars["resume_minutes"].get() * 60
                if idle >= wait:
                    self.resume_calc(auto=True)
                else:
                    info += f"   |   reprise dans {fmt_mmss(wait - idle)}"
        except tk.TclError:
            pass  # champ numérique vide pendant la saisie
        self.idle_lbl.configure(text=info)

        self.after(500, self.tick)

    def on_close(self):
        if self.proc is not None:
            if not messagebox.askyesno("Quitter", "BEAST tourne encore. Tout arrêter et quitter ?"):
                return
            self.stop()
        self.save_settings()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
