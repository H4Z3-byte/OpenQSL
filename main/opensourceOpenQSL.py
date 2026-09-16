import html
import os
import re
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import unquote, urljoin, urlsplit

import requests

import tkinter as tk
from tkinter import ttk, messagebox

# Configurazione velocità e retry
MAX_WORKERS = 8
MAX_RETRIES = 50  # Porta i tentativi fino a 50 per completare tutto al 100%

BASE = "https://www.eqsl.cc"

BG_COLOR = "#121212"
FG_COLOR = "#FFB000"
ALT_BG_COLOR = "#1E1E1E"
HIGHLIGHT_COLOR = "#FFC83B"
BTN_BG = "#2B2B2B"
BTN_ACTIVE_BG = "#3D3D3D"
FONT_FAMILY = "Courier"

I18N = {
    "IT": {
        "title": "=== OpenQSL Terminal ===",
        "auth_frame": " [ 1. AUTENTICAZIONE ] ",
        "callsign": "CALLSIGN :",
        "password": "PASSWORD :",
        "login_btn": "[ LOGIN ]",
        "band_frame": " [ 2. SELEZIONE BANDA ] ",
        "bands_lbl": "BANDE TROVATE:",
        "console_frame": " [ CONSOLE OUTPUT ] ",
        "download_btn": ">>> AVVIA\nDOWNLOAD <<<",
        "ready": "> LINGUA SELEZIONATA: ITALIANO.\n> Inserisci le credenziali e premi LOGIN.",
        "err_creds": "Inserisci sia Callsign che Password.",
        "connecting": "> Connessione a eQSL.cc per [{}]...",
        "login_ok": "> Login effettuato con successo!",
        "fetching_bands": "> Recupero elenco bande disponibili...",
        "login_fail": "Login fallito: controlla callsign e password.",
        "no_bands": "! Nessuna banda o cartolina trovata nell'account.",
        "bands_found": "> Trovate {} bande attive.",
        "all_bands": "Tutte le bande (ALL)",
        "starting_extract": "> Avvio estrazione link cartoline per banda: {}...",
        "extract_err": "! Errore lettura banda {}: {}",
        "no_cards": "! Nessuna cartolina trovata da scaricare.",
        "found_total": "> Trovate {} cartoline disponibili. Scaricamento in corso...",
        "progress_msg": ">> SCARICAMENTO: [{}] {:3.0f}% ({}/{} - Fail: {})",
        "retry_msg": "> RECUPERO (Tentativo {}/{}): Riprovo le {} cartoline non ancora generate...",
        "no_images": "! Nessuna immagine scaricata correttamente.",
        "zipping": "> Compressione in corso: {}",
        "success_title": "Operazione Completata",
        "success_msg": "Scaricamento completato!\nFile ZIP salvato in:\n{}",
        "warning_failed": "WARNING: {} cartoline non scaricate dopo 50 tentativi."
    },
    "EN": {
        "title": "=== OpenQSL Terminal ===",
        "auth_frame": " [ 1. AUTHENTICATION ] ",
        "callsign": "CALLSIGN :",
        "password": "PASSWORD :",
        "login_btn": "[ LOGIN ]",
        "band_frame": " [ 2. BAND SELECTION ] ",
        "bands_lbl": "BANDS FOUND:",
        "console_frame": " [ CONSOLE OUTPUT ] ",
        "download_btn": ">>> START\nDOWNLOAD <<<",
        "ready": "> LANGUAGE SELECTED: ENGLISH.\n> Enter credentials and click LOGIN.",
        "err_creds": "Please enter both Callsign and Password.",
        "connecting": "> Connecting to eQSL.cc for [{}]...",
        "login_ok": "> Login successful!",
        "fetching_bands": "> Fetching available bands list...",
        "login_fail": "Login failed: check callsign and password.",
        "no_bands": "! No bands or cards found in account.",
        "bands_found": "> Found {} active bands.",
        "all_bands": "All bands (ALL)",
        "starting_extract": "> Extracting card links for band: {}...",
        "extract_err": "! Network error on band {}: {}",
        "no_cards": "! No cards found to download.",
        "found_total": "> Found {} available cards. Downloading in progress...",
        "progress_msg": ">> DOWNLOADING: [{}] {:3.0f}% ({}/{} - Fail: {})",
        "retry_msg": "> RETRY (Attempt {}/{}): Retrying {} pending cards...",
        "no_images": "! No images downloaded successfully.",
        "zipping": "> Compressing files: {}",
        "success_title": "Task Completed",
        "success_msg": "Download completed!\nZIP archive saved at:\n{}",
        "warning_failed": "WARNING: {} cards failed to download after 50 attempts."
    }
}

class OpenQSLRetroApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.lang = "IT"
        self.txt = I18N[self.lang]

        self.title("=== OpenQSL Terminal ===")
        self.geometry("680x640")
        self.minsize(600, 520)
        self.configure(bg=BG_COLOR)

        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Connection": "keep-alive"
        })

        self.bands_data = {}
        self._progress_line_index = None

        self._setup_retro_styles()
        self._create_widgets()

    def _setup_retro_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clamp")
        except tk.TclError:
            pass

    def _create_widgets(self):
        main_frame = tk.Frame(self, bg=BG_COLOR, bd=3, relief="groove")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        top_bar = tk.Frame(main_frame, bg=BG_COLOR)
        top_bar.pack(fill="x", padx=5, pady=(2, 5))

        tk.Label(top_bar, text="LANG:", font=(FONT_FAMILY, 9, "bold"), bg=BG_COLOR, fg=FG_COLOR).pack(side="left")
        
        btn_it = tk.Button(top_bar, text="[ IT ]", font=(FONT_FAMILY, 8, "bold"), bg=BTN_BG, fg=FG_COLOR,
                           activebackground=BTN_ACTIVE_BG, activeforeground=HIGHLIGHT_COLOR, bd=1, relief="raised",
                           command=lambda: self.set_language("IT"))
        btn_it.pack(side="left", padx=2)

        btn_en = tk.Button(top_bar, text="[ EN ]", font=(FONT_FAMILY, 8, "bold"), bg=BTN_BG, fg=FG_COLOR,
                           activebackground=BTN_ACTIVE_BG, activeforeground=HIGHLIGHT_COLOR, bd=1, relief="raised",
                           command=lambda: self.set_language("EN"))
        btn_en.pack(side="left", padx=2)

        self.cred_frame = tk.LabelFrame(main_frame, text=self.txt["auth_frame"], font=(FONT_FAMILY, 9, "bold"),
                                   bg=BG_COLOR, fg=FG_COLOR, bd=2, relief="ridge", labelanchor="nw")
        self.cred_frame.pack(fill="x", padx=10, pady=5)

        self.lbl_call = tk.Label(self.cred_frame, text=self.txt["callsign"], font=(FONT_FAMILY, 9, "bold"), bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_call.grid(row=0, column=0, padx=5, pady=5, sticky="e")
        
        self.ent_callsign = tk.Entry(self.cred_frame, font=(FONT_FAMILY, 10), bg=ALT_BG_COLOR, fg=FG_COLOR, insertbackground=FG_COLOR, bd=1, relief="solid")
        self.ent_callsign.grid(row=0, column=1, padx=5, pady=5, sticky="we")

        self.lbl_pass = tk.Label(self.cred_frame, text=self.txt["password"], font=(FONT_FAMILY, 9, "bold"), bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_pass.grid(row=0, column=2, padx=5, pady=5, sticky="e")
        
        self.ent_password = tk.Entry(self.cred_frame, show="*", font=(FONT_FAMILY, 10), bg=ALT_BG_COLOR, fg=FG_COLOR, insertbackground=FG_COLOR, bd=1, relief="solid")
        self.ent_password.grid(row=0, column=3, padx=5, pady=5, sticky="we")

        self.cred_frame.columnconfigure(1, weight=1)
        self.cred_frame.columnconfigure(3, weight=1)

        self.btn_login = tk.Button(self.cred_frame, text=self.txt["login_btn"], font=(FONT_FAMILY, 9, "bold"),
                                   bg=BTN_BG, fg=FG_COLOR, activebackground=BTN_ACTIVE_BG, activeforeground=HIGHLIGHT_COLOR,
                                   bd=2, relief="raised", command=self.on_login_click)
        self.btn_login.grid(row=0, column=4, padx=10, pady=5)

        self.band_frame = tk.LabelFrame(main_frame, text=self.txt["band_frame"], font=(FONT_FAMILY, 9, "bold"),
                                   bg=BG_COLOR, fg=FG_COLOR, bd=2, relief="ridge", labelanchor="nw")
        self.band_frame.pack(fill="x", padx=10, pady=5)

        self.lbl_bands = tk.Label(self.band_frame, text=self.txt["bands_lbl"], font=(FONT_FAMILY, 9), bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_bands.pack(anchor="w", padx=5, pady=(2, 2))

        band_container = tk.Frame(self.band_frame, bg=BG_COLOR)
        band_container.pack(fill="x", padx=5, pady=5)

        list_frame = tk.Frame(band_container, bg=BG_COLOR)
        list_frame.pack(side="left", fill="both", expand=True)

        self.lst_bands = tk.Listbox(list_frame, font=(FONT_FAMILY, 9), bg=ALT_BG_COLOR, fg=FG_COLOR,
                                    selectbackground=FG_COLOR, selectforeground=BG_COLOR,
                                    height=5, bd=1, relief="solid", exportselection=False)
        self.lst_bands.pack(side="left", fill="both", expand=True)

        lst_scroll = tk.Scrollbar(list_frame, command=self.lst_bands.yview, bg=BG_COLOR, activebackground=BTN_BG)
        lst_scroll.pack(side="right", fill="y")
        self.lst_bands.config(yscrollcommand=lst_scroll.set)

        self.btn_download = tk.Button(band_container, text=self.txt["download_btn"], font=(FONT_FAMILY, 10, "bold"),
                                      bg=BTN_BG, fg=FG_COLOR, activebackground=BTN_ACTIVE_BG, activeforeground=HIGHLIGHT_COLOR,
                                      bd=3, relief="raised", state="disabled", width=15, command=self.on_download_click)
        self.btn_download.pack(side="right", fill="y", padx=(10, 0))

        self.log_frame = tk.LabelFrame(main_frame, text=self.txt["console_frame"], font=(FONT_FAMILY, 9, "bold"),
                                  bg=BG_COLOR, fg=FG_COLOR, bd=2, relief="ridge", labelanchor="nw")
        self.log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.txt_log = tk.Text(self.log_frame, font=(FONT_FAMILY, 9), bg=BG_COLOR, fg=FG_COLOR,
                               insertbackground=FG_COLOR, bd=0, highlightthickness=0)
        self.txt_log.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        scrollbar = tk.Scrollbar(self.log_frame, command=self.txt_log.yview, bg=BG_COLOR, activebackground=BTN_BG)
        scrollbar.pack(side="right", fill="y")
        self.txt_log.config(yscrollcommand=scrollbar.set)

        self.log_message(self.txt["ready"])

    def set_language(self, lang):
        self.lang = lang
        self.txt = I18N[self.lang]
        self.cred_frame.config(text=self.txt["auth_frame"])
        self.lbl_call.config(text=self.txt["callsign"])
        self.lbl_pass.config(text=self.txt["password"])
        self.btn_login.config(text=self.txt["login_btn"])
        self.band_frame.config(text=self.txt["band_frame"])
        self.lbl_bands.config(text=self.txt["bands_lbl"])
        self.log_frame.config(text=self.txt["console_frame"])
        self.btn_download.config(text=self.txt["download_btn"])
        self.log_message(self.txt["ready"])

    def log_message(self, text):
        self.txt_log.config(state="normal")
        self.txt_log.insert(tk.END, f"{text}\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state="disabled")
        self._progress_line_index = None

    def update_ascii_progress(self, current, total, failed, bar_length=20):
        self.txt_log.config(state="normal")

        percent = (current / total) * 100 if total > 0 else 0
        filled = int(round(bar_length * current / float(total))) if total > 0 else 0
        bar = "*" * filled + " " * (bar_length - filled)

        msg = self.txt["progress_msg"].format(bar, percent, current, total, failed)

        if self._progress_line_index is None:
            self.txt_log.insert(tk.END, f"{msg}\n")
            line_count = int(self.txt_log.index("end-1c").split(".")[0]) - 1
            self._progress_line_index = f"{line_count}.0"
        else:
            line_end = f"{self._progress_line_index} lineend"
            self.txt_log.delete(self._progress_line_index, line_end)
            self.txt_log.insert(self._progress_line_index, msg)

        self.txt_log.see(tk.END)
        self.txt_log.config(state="disabled")

    def on_login_click(self):
        callsign = self.ent_callsign.get().strip()
        password = self.ent_password.get().strip()

        if not callsign or not password:
            messagebox.showwarning("Warning" if self.lang == "EN" else "Attenzione", self.txt["err_creds"])
            return

        self.btn_login.config(state="disabled")
        self.log_message(self.txt["connecting"].format(callsign))

        threading.Thread(target=self._async_login, args=(callsign, password), daemon=True).start()

    def _async_login(self, callsign, password):
        try:
            self.session.post(
                f"{BASE}/QSLCard/LoginFinish.cfm",
                data={
                    "Callsign": callsign,
                    "EnteredPassword": password,
                    "Login": "Go",
                    "ZeroType": "Slash",
                },
                allow_redirects=True,
            )
            probe = self.session.get(f"{BASE}/QSLCard/InBoxSelector.cfm?Archive=1")
            if "Please go to the" in probe.text and "Login Page" in probe.text:
                raise RuntimeError(self.txt["login_fail"])

            self.log_message(self.txt["login_ok"])
            self.log_message(self.txt["fetching_bands"])

            self.bands_data = {}
            for archive in (0, 1):
                text = self.session.get(f"{BASE}/QSLCard/InBoxSelector.cfm?Archive={archive}").text
                for m in re.finditer(
                    r"Inbox\.cfm\?Archive=(\d)(?:&amp;|&)Reject=0(?:&amp;|&)LimitBand=([^\"'&]+)",
                    text,
                ):
                    band = unquote(m.group(2)).strip()
                    count = 0
                    nxt = text[m.end():m.end() + 400]
                    cm = re.search(r">\s*(\d+)\s*<", nxt)
                    if cm:
                        count = int(cm.group(1))
                    self.bands_data.setdefault(band, {"count": 0})
                    self.bands_data[band]["count"] += count

            if not self.bands_data:
                self.log_message(self.txt["no_bands"])
                self.btn_login.config(state="normal")
                return

            ordered = sorted(self.bands_data, key=lambda b: self.bands_data[b]["count"], reverse=True)
            card_lbl = "QSO" if self.lang == "IT" else "QSOs"

            self.lst_bands.delete(0, tk.END)
            for b in ordered:
                self.lst_bands.insert(tk.END, f"{b} ({self.bands_data[b]['count']} {card_lbl})")
            self.lst_bands.insert(tk.END, self.txt["all_bands"])

            self.lst_bands.selection_set(0)

            self.log_message(self.txt["bands_found"].format(len(ordered)))
            self.btn_download.config(state="normal")

        except Exception as exc:
            self.log_message(f"! ERRORE: {exc}")
            self.btn_login.config(state="normal")

    def on_download_click(self):
        sel_idx = self.lst_bands.curselection()
        if not sel_idx:
            return

        selection = self.lst_bands.get(sel_idx[0])

        if self.txt["all_bands"] in selection or "ALL" in selection:
            chosen_band = "ALL"
        else:
            chosen_band = selection.split(" ")[0]

        self.btn_download.config(state="disabled")
        self.btn_login.config(state="disabled")

        threading.Thread(target=self._async_download, args=(chosen_band,), daemon=True).start()

    def _async_download(self, band):
        callsign = self.ent_callsign.get().strip()
        band_list = list(self.bands_data) if band == "ALL" else [band]

        self.log_message(self.txt["starting_extract"].format(band))

        tmp_dir = os.path.join(os.environ.get("TEMP", "."), "eqsl_cards_dl")
        os.makedirs(tmp_dir, exist_ok=True)

        tasks = []
        for current in band_list:
            try:
                page_urls = self._get_card_urls(current)
                for card_url in page_urls:
                    tasks.append(self._parse_card(card_url))
            except Exception as exc:
                self.log_message(self.txt["extract_err"].format(current, exc))

        total = len(tasks)
        if total == 0:
            self.log_message(self.txt["no_cards"])
            self.btn_download.config(state="normal")
            return

        self.log_message(self.txt["found_total"].format(total))

        ok = 0
        failed_cards = list(tasks)
        self._progress_line_index = None

        # LOOP DINAMICO FINO A 50 TENTATIVI SULLE FALLITE
        for attempt in range(1, MAX_RETRIES + 1):
            if not failed_cards:
                break

            if attempt > 1:
                self.log_message(self.txt["retry_msg"].format(attempt, MAX_RETRIES, len(failed_cards)))
                # Piccola pausa tattica per dare tempo al server eQSL di compilare le immagini mancanti
                time.sleep(1)

            current_fails = list(failed_cards)
            failed_cards.clear()
            self._progress_line_index = None

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                future_to_card = {pool.submit(self._download_image, card): card for card in current_fails}
                for fut in as_completed(future_to_card):
                    card = future_to_card[fut]
                    try:
                        res = fut.result()
                    except Exception:
                        res = None

                    if res is None:
                        failed_cards.append(card)
                    else:
                        name, data = res
                        with open(os.path.join(tmp_dir, name), "wb") as fh:
                            fh.write(data)
                        ok += 1

                    self.update_ascii_progress(ok, total, len(failed_cards))

        if ok == 0:
            self.log_message(self.txt["no_images"])
            self.btn_download.config(state="normal")
            return

        label = "Tutte" if band == "ALL" else band
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_call = re.sub(r'[<>:"/\\|?*]+', "_", callsign)
        safe_label = re.sub(r'[<>:"/\\|?*]+', "_", label)

        default_zip_name = f"eqsl_{safe_call}_{safe_label}_{stamp}.zip"
        download_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        zip_path = os.path.join(download_dir, default_zip_name)

        self.log_message(self.txt["zipping"].format(zip_path))

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in os.listdir(tmp_dir):
                zf.write(os.path.join(tmp_dir, name), arcname=name)

        for name in os.listdir(tmp_dir):
            os.remove(os.path.join(tmp_dir, name))
        os.rmdir(tmp_dir)

        final_failed = len(failed_cards)
        self.log_message("===========================================")
        self.log_message(f" SUCCESS! {ok}/{total} images saved in:")
        self.log_message(f" {zip_path}")
        if final_failed > 0:
            self.log_message(self.txt["warning_failed"].format(final_failed))
        self.log_message("===========================================")

        messagebox.showinfo(self.txt["success_title"], self.txt["success_msg"].format(zip_path))
        self.btn_download.config(state="normal")

    def _get_card_urls(self, band):
        urls = set()
        for archive in (0, 1):
            page = f"{BASE}/QSLCard/Inbox.cfm?Archive={archive}&Reject=0&LimitBand={band}"
            resp = self.session.get(page)
            urls.update(self._extract_display_urls(resp.text))
        return sorted(urls)

    def _extract_display_urls(self, text):
        urls = []
        patterns = [
            r"popupPrintPage\((?:[^)]*?)(DisplayeQSL\.cfm\?[^'\"#<>)]*)",
            r"href=[\"']?(DisplayeQSL\.cfm\?[^'\"#<> ]*)",
            r"href=[\"']?(DisplayImage\.cfm\?[^'\"#<> ]*)",
        ]
        
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                u = html.unescape(m.group(1))
                relative_path = "QSLCard/" + u if not u.startswith("QSLCard/") else u
                urls.append(urljoin(BASE, relative_path))
        return list(set(urls))

    def _parse_card(self, page_url):
        qs = unquote(urlsplit(page_url).query)
        def grab(name):
            m = re.search(rf"[?&]{re.escape(name)}=([^&]*)", qs)
            return m.group(1) if m else ""

        return {
            "card_url": page_url,
            "sender": grab("Callsign"),
            "me": grab("VisitorCallsign"),
            "qso_date": grab("QSODate"),
            "band": grab("Band"),
            "mode": grab("Mode"),
        }

    def _download_image(self, card):
        try:
            resp = self.session.get(card["card_url"], timeout=8)
            
            if resp.headers.get("Content-Type", "").startswith("image/"):
                ext = ".png" if "png" in resp.headers.get("Content-Type", "") else ".jpg"
                stamp = card["qso_date"].replace(".0", "").replace(":00", "")
                stamp = re.sub(r"[-:]", "", stamp).replace(" ", "_")
                base = f"{card['me']}_{stamp}_{card['sender']}_{card['band']}_{card['mode']}"
                safe = re.sub(r'[<>:"/\\|?*]+', "_", base) or "card"
                return safe + ext, resp.content

            img_url = None
            
            m1 = re.search(r'<img[^>]+src=["\'](/CFFileServlet/_cf_image/[^"\']+)["\']', resp.text, re.IGNORECASE)
            if m1:
                img_url = urljoin(BASE, m1.group(1))
            
            if not img_url:
                m2 = re.search(r'<img[^>]+src=["\']([^"\']*(?:GeteQSL|DisplayImage)[^"\']*)["\']', resp.text, re.IGNORECASE)
                if m2:
                    img_url = urljoin(card["card_url"], m2.group(1))

            if not img_url:
                m3 = re.search(r'<img[^>]+src=["\']([^"\']+\.(?:jpg|png|gif|jpeg)[^"\']*)["\']', resp.text, re.IGNORECASE)
                if m3:
                    img_url = urljoin(card["card_url"], m3.group(1))

            if img_url:
                img_resp = self.session.get(img_url, timeout=8)
                if img_resp.status_code == 200 and len(img_resp.content) > 500:
                    ext = ".png"
                    if ".jpg" in img_url.lower() or ".jpeg" in img_url.lower():
                        ext = ".jpg"
                    elif ".gif" in img_url.lower():
                        ext = ".gif"

                    stamp = card["qso_date"].replace(".0", "").replace(":00", "")
                    stamp = re.sub(r"[-:]", "", stamp).replace(" ", "_")
                    base = f"{card['me']}_{stamp}_{card['sender']}_{card['band']}_{card['mode']}"
                    safe = re.sub(r'[<>:"/\\|?*]+', "_", base) or "card"
                    return safe + ext, img_resp.content

        except requests.RequestException:
            pass

        return None


if __name__ == "__main__":
    app = OpenQSLRetroApp()
    app.mainloop()
