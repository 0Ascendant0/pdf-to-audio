#!/usr/bin/env python3
"""Black-theme GUI for book2audio: edit a PDF/EPUB, then turn it into audio.

Run:  python app.py
Needs: pip install -r requirements.txt   (Linux also: sudo apt install python3-tk)
"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

import book2audio
import editlib
import exporters

# ---- palette: pure black, hairline borders, white accent ----
BG = "#000000"
PANEL = "#0A0A0A"
BORDER = "#2A2A2A"
FG = "#EDEDED"
MUTED = "#808080"
ACCENT = "#FFFFFF"
ACCENT_HOVER = "#BDBDBD"
DANGER = "#FF4D4D"

VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sarah",
    "am_michael", "am_adam",
    "bf_emma", "bf_isabella",
    "bm_george", "bm_lewis",
]

ctk.set_appearance_mode("dark")

FONT = "Segoe UI" if sys.platform == "win32" else "Helvetica"
MONO = "Consolas" if sys.platform == "win32" else "Menlo"

# tab names double as button labels, so they carry their own padding
TAB_CONVERT = "    CONVERT    "
TAB_EDIT = "    EDIT    "


# ---------- small widget helpers (all square-cornered) ----------
def label(parent, text, muted=False, size=12, bold=False):
    return ctk.CTkLabel(
        parent, text=text, text_color=MUTED if muted else FG,
        font=(FONT, size, "bold" if bold else "normal"), anchor="w",
    )


def entry(parent, var, fg=PANEL):
    return ctk.CTkEntry(
        parent, textvariable=var, corner_radius=0, border_width=1,
        border_color=BORDER, fg_color=fg, text_color=FG, height=34, font=(FONT, 12),
    )


def button(parent, text, command, primary=False, danger=False, width=110):
    if primary:
        kw = dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#000000", border_width=0)
    elif danger:
        kw = dict(fg_color=BG, hover_color="#1A0A0A", text_color=DANGER, border_width=1, border_color=DANGER)
    else:
        kw = dict(fg_color=BG, hover_color="#1A1A1A", text_color=FG, border_width=1, border_color=BORDER)
    return ctk.CTkButton(
        parent, text=text, command=command, corner_radius=0, height=34,
        width=width, font=(FONT, 11, "bold"), **kw,
    )


def check(parent, text, var):
    return ctk.CTkCheckBox(
        parent, text=text, variable=var, corner_radius=0, border_width=1,
        checkbox_width=16, checkbox_height=16, fg_color=ACCENT, hover_color=ACCENT_HOVER,
        border_color=BORDER, checkmark_color="#000000", text_color=FG, font=(FONT, 12),
    )


def option_menu(parent, values, var, width=170):
    return ctk.CTkOptionMenu(
        parent, values=values, variable=var, corner_radius=0, height=34, width=width,
        fg_color=PANEL, button_color=BORDER, button_hover_color="#3A3A3A",
        text_color=FG, dropdown_fg_color=PANEL, dropdown_hover_color="#1F1F1F",
        dropdown_text_color=FG, font=(FONT, 12),
    )


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("BOOK → AUDIO")
        self.geometry("1000x780")
        self.minsize(860, 660)
        self.configure(fg_color=BG)

        self.q = queue.Queue()
        self.cancel_flag = threading.Event()
        self.worker = None

        # convert tab vars
        self.in_var = ctk.StringVar()
        self.out_var = ctk.StringVar(value=str(Path.home() / "audiobooks"))
        self.voice_var = ctk.StringVar(value=VOICES[0])
        self.speed_var = ctk.DoubleVar(value=1.0)

        # editor state
        self.chapters = []          # [[name, text], ...] (the working, edited copy)
        self.original = {}          # name -> original text
        self.loaded_path = None
        self.cur = None             # index of chapter shown in the editor
        self._match = None          # (chapter_idx, start, end) of the highlighted match
        self._labels = []
        self._commit_job = None
        self.find_var = ctk.StringVar()
        self.repl_var = ctk.StringVar()
        self.case_var = ctk.BooleanVar(value=False)
        self.word_var = ctk.BooleanVar(value=False)
        self.regex_var = ctk.BooleanVar(value=False)
        self.fmt_var = ctk.StringVar(value="EPUB")

        self._build()
        self.after(100, self._poll)

    # =====================================================================
    # layout
    # =====================================================================
    def _build(self):
        head = ctk.CTkFrame(self, corner_radius=0, fg_color=BG)
        head.pack(fill="x", padx=28, pady=(22, 6))
        label(head, "BOOK → AUDIO", size=22, bold=True).pack(anchor="w")
        label(head, "Edit, export and convert PDF and EPUB books. Fully offline.",
              muted=True).pack(anchor="w", pady=(2, 0))

        self.tabs = ctk.CTkTabview(
            self, corner_radius=0, fg_color=BG, border_width=1, border_color=BORDER,
            segmented_button_fg_color=BG, segmented_button_selected_color="#1F1F1F",
            segmented_button_selected_hover_color="#2A2A2A",
            segmented_button_unselected_color=BG, segmented_button_unselected_hover_color="#141414",
            text_color=FG, anchor="w",
        )
        self.tabs.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self._build_convert(self.tabs.add(TAB_CONVERT))
        self._build_edit(self.tabs.add(TAB_EDIT))
        self.tabs._segmented_button.configure(font=(FONT, 12, "bold"), height=38)

    # ---------- CONVERT tab ----------
    def _build_convert(self, parent):
        root = ctk.CTkFrame(parent, corner_radius=0, fg_color=BG)
        root.pack(fill="both", expand=True, padx=8, pady=8)
        root.grid_columnconfigure(0, weight=1)

        label(root, "INPUT FILE", muted=True, size=10, bold=True).grid(row=0, column=0, sticky="w")
        row = ctk.CTkFrame(root, corner_radius=0, fg_color=BG)
        row.grid(row=1, column=0, sticky="ew", pady=(4, 14))
        row.grid_columnconfigure(0, weight=1)
        entry(row, self.in_var).grid(row=0, column=0, sticky="ew")
        button(row, "BROWSE", self._pick_file).grid(row=0, column=1, padx=(8, 0))

        label(root, "OUTPUT FOLDER", muted=True, size=10, bold=True).grid(row=2, column=0, sticky="w")
        row = ctk.CTkFrame(root, corner_radius=0, fg_color=BG)
        row.grid(row=3, column=0, sticky="ew", pady=(4, 14))
        row.grid_columnconfigure(0, weight=1)
        entry(row, self.out_var).grid(row=0, column=0, sticky="ew")
        button(row, "BROWSE", self._pick_folder).grid(row=0, column=1, padx=(8, 0))

        opts = ctk.CTkFrame(root, corner_radius=0, fg_color=BG)
        opts.grid(row=4, column=0, sticky="ew", pady=(0, 18))
        opts.grid_columnconfigure(1, weight=1)

        v = ctk.CTkFrame(opts, corner_radius=0, fg_color=BG)
        v.grid(row=0, column=0, sticky="w")
        label(v, "VOICE", muted=True, size=10, bold=True).pack(anchor="w")
        option_menu(v, VOICES, self.voice_var).pack(anchor="w", pady=(4, 0))

        s = ctk.CTkFrame(opts, corner_radius=0, fg_color=BG)
        s.grid(row=0, column=1, sticky="ew", padx=(28, 0))
        self.speed_label = label(s, "SPEED  1.00x", muted=True, size=10, bold=True)
        self.speed_label.pack(anchor="w")
        ctk.CTkSlider(
            s, from_=0.7, to=1.3, number_of_steps=12, variable=self.speed_var,
            command=self._on_speed, corner_radius=0, button_corner_radius=0,
            fg_color=BORDER, progress_color=ACCENT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, height=18,
        ).pack(fill="x", pady=(10, 0))

        act = ctk.CTkFrame(root, corner_radius=0, fg_color=BG)
        act.grid(row=5, column=0, sticky="ew", pady=(0, 14))
        self.start_btn = button(act, "CONVERT", self._start, primary=True, width=140)
        self.start_btn.pack(side="left")
        self.cancel_btn = button(act, "CANCEL", self._cancel, danger=True)
        self.cancel_btn.pack(side="left", padx=(8, 0))
        self.cancel_btn.configure(state="disabled")
        button(act, "OPEN FOLDER", self._open_folder).pack(side="right")

        self.bar = ctk.CTkProgressBar(root, corner_radius=0, height=6,
                                      fg_color=BORDER, progress_color=ACCENT)
        self.bar.set(0)
        self.bar.grid(row=6, column=0, sticky="ew", pady=(0, 14))

        label(root, "LOG", muted=True, size=10, bold=True).grid(row=7, column=0, sticky="w")
        self.log_box = ctk.CTkTextbox(
            root, corner_radius=0, border_width=1, border_color=BORDER,
            fg_color=PANEL, text_color=FG, font=(MONO, 11), state="disabled", wrap="word",
        )
        self.log_box.grid(row=8, column=0, sticky="nsew", pady=(4, 0))
        root.grid_rowconfigure(8, weight=1)

    # ---------- EDIT tab ----------
    def _build_edit(self, parent):
        root = ctk.CTkFrame(parent, corner_radius=0, fg_color=BG)
        root.pack(fill="both", expand=True, padx=8, pady=8)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        # top bar: open / export
        bar = ctk.CTkFrame(root, corner_radius=0, fg_color=BG)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        bar.grid_columnconfigure(1, weight=1)
        button(bar, "OPEN BOOK", self._open_book, primary=True, width=120).grid(row=0, column=0)
        self.loaded_label = label(bar, "No book loaded. Open a .pdf or .epub to edit it.", muted=True)
        self.loaded_label.grid(row=0, column=1, sticky="w", padx=12)
        option_menu(bar, ["EPUB", "PDF", "TXT"], self.fmt_var, width=90).grid(row=0, column=2)
        button(bar, "EXPORT", self._export, width=100).grid(row=0, column=3, padx=(8, 0))

        # find / replace panel
        fr = ctk.CTkFrame(root, corner_radius=0, fg_color=PANEL, border_width=1, border_color=BORDER)
        fr.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        fr.grid_columnconfigure(1, weight=1)

        label(fr, "FIND", muted=True, size=10, bold=True).grid(row=0, column=0, padx=(12, 10), pady=(12, 6), sticky="w")
        self.find_entry = entry(fr, self.find_var, fg=BG)
        self.find_entry.grid(row=0, column=1, sticky="ew", pady=(12, 6))
        button(fr, "FIND NEXT", self._find_next, primary=True, width=110).grid(
            row=0, column=2, padx=12, pady=(12, 6), sticky="w")

        label(fr, "REPLACE", muted=True, size=10, bold=True).grid(row=1, column=0, padx=(12, 10), pady=6, sticky="w")
        self.repl_entry = entry(fr, self.repl_var, fg=BG)
        self.repl_entry.grid(row=1, column=1, sticky="ew", pady=6)
        btns = ctk.CTkFrame(fr, corner_radius=0, fg_color=PANEL)
        btns.grid(row=1, column=2, padx=12, pady=6, sticky="w")
        button(btns, "REPLACE", self._replace_one, width=90).pack(side="left")
        button(btns, "ALL IN CHAPTER", lambda: self._replace_all(False), width=130).pack(side="left", padx=(6, 0))
        button(btns, "ALL IN BOOK", lambda: self._replace_all(True), width=110).pack(side="left", padx=(6, 0))

        opts = ctk.CTkFrame(fr, corner_radius=0, fg_color=PANEL)
        opts.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(4, 12))
        check(opts, "Match case", self.case_var).pack(side="left")
        check(opts, "Whole word", self.word_var).pack(side="left", padx=(18, 0))
        check(opts, "Regex", self.regex_var).pack(side="left", padx=(18, 0))
        button(opts, "REVERT CHAPTER", self._revert_chapter, danger=True, width=140).pack(side="right")

        # chapter list + editor
        content = ctk.CTkFrame(root, corner_radius=0, fg_color=BG)
        content.grid(row=2, column=0, sticky="nsew")
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)

        lf = ctk.CTkFrame(content, corner_radius=0, fg_color=BG)
        lf.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        self.listbox = tk.Listbox(
            lf, width=24, bg=PANEL, fg=FG, selectbackground="#2A2A2A", selectforeground=ACCENT,
            activestyle="none", highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=BORDER, borderwidth=0, relief="flat", exportselection=False,
            font=(FONT, 11),
        )
        sb = ctk.CTkScrollbar(lf, corner_radius=0, fg_color=BG, button_color=BORDER,
                              button_hover_color="#444444", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="y")
        sb.pack(side="left", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_list_select)

        self.editor = ctk.CTkTextbox(
            content, corner_radius=0, border_width=1, border_color=BORDER,
            fg_color=PANEL, text_color=FG, font=(FONT, 13), wrap="word",
            undo=True, state="disabled",
        )
        self.editor.grid(row=0, column=1, sticky="nsew")
        self.editor._textbox.tag_configure("match", background=ACCENT, foreground="#000000")
        self.editor.bind("<KeyRelease>", lambda e: self._commit_soon())

        self.edit_status = label(root, "", muted=True, size=11)
        self.edit_status.grid(row=3, column=0, sticky="w", pady=(8, 0))

        # keyboard shortcuts
        self.find_entry.bind("<Return>", lambda e: self._find_next())
        self.repl_entry.bind("<Return>", lambda e: self._replace_one())
        self.bind_all("<Control-f>", lambda e: self._focus_find())
        self.bind_all("<Command-f>", lambda e: self._focus_find())

    # =====================================================================
    # CONVERT tab handlers
    # =====================================================================
    def _on_speed(self, value):
        self.speed_label.configure(text=f"SPEED  {value:.2f}x")

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Choose a book", filetypes=[("Books", "*.pdf *.epub"), ("All files", "*.*")])
        if path:
            self.in_var.set(path)

    def _pick_folder(self):
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.out_var.set(path)

    def _open_folder(self):
        folder = Path(self.out_var.get())
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(folder)])
        else:
            subprocess.run(["xdg-open", str(folder)])

    def _log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _start(self):
        src = Path(self.in_var.get().strip())
        if not src.is_file() or src.suffix.lower() not in (".pdf", ".epub"):
            self._log("Choose a valid .pdf or .epub file first.")
            return

        # If this book is open in the editor, convert the edited text.
        chapters = None
        if self.chapters and self.loaded_path and src.resolve() == self.loaded_path.resolve():
            self._commit()
            chapters = [(n, t) for n, t in self.chapters]
            changed = sum(1 for n, t in chapters if t != self.original[n])
            self._log(f"Using text from the EDIT tab ({changed} chapter(s) edited).")

        self.cancel_flag.clear()
        self.bar.set(0)
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        args = (src, self.out_var.get().strip(), self.voice_var.get(),
                round(self.speed_var.get(), 2), chapters)
        self.worker = threading.Thread(target=self._run, args=args, daemon=True)
        self.worker.start()

    def _cancel(self):
        self.cancel_flag.set()
        self.cancel_btn.configure(state="disabled")
        self._log("Cancelling after the current paragraph...")

    def _run(self, src, out, voice, speed, chapters):
        try:
            book2audio.convert(
                src, out, voice, speed,
                log=lambda m: self.q.put(("log", m)),
                progress=lambda f: self.q.put(("progress", f)),
                cancel=self.cancel_flag.is_set,
                chapters=chapters,
            )
        except Exception as e:  # surface errors in the log instead of dying silently
            self.q.put(("log", f"Error: {e}"))
        self.q.put(("done", None))

    # =====================================================================
    # EDIT tab: loading, chapters
    # =====================================================================
    def _status(self, msg):
        self.edit_status.configure(text=msg)

    def _focus_find(self):
        self.tabs.set(TAB_EDIT)
        self.find_entry.focus_set()
        self.find_entry.select_range(0, "end")

    def _open_book(self):
        path = filedialog.askopenfilename(
            title="Open a book to edit", filetypes=[("Books", "*.pdf *.epub"), ("All files", "*.*")])
        if not path:
            return
        self.in_var.set(path)
        self._status("Loading...")
        threading.Thread(target=self._load_worker, args=(Path(path),), daemon=True).start()

    def _load_worker(self, path):
        try:
            self.q.put(("loaded", (path, book2audio.load_chapters(path))))
        except Exception as e:
            self.q.put(("edit_status", f"Could not open: {e}"))

    def _on_loaded(self, path, chapters):
        self.loaded_path = path
        self.chapters = [[n, t] for n, t in chapters]
        self.original = {n: t for n, t in chapters}
        self.cur = None
        self._match = None
        self._labels = []
        self.listbox.delete(0, "end")
        for n, _ in self.chapters:
            lab = "  " + n
            self._labels.append(lab)
            self.listbox.insert("end", lab)
        self.loaded_label.configure(text=f"{path.name}   ·   {len(self.chapters)} chapters")
        self._select(0)
        self._status("Loaded. Edit the text, or use Find / Replace.")

    def _on_list_select(self, _event):
        sel = self.listbox.curselection()
        if sel and sel[0] != self.cur:
            self._select(sel[0], update_list=False)

    def _select(self, idx, update_list=True, commit=True):
        if commit:  # skip when the working copy was just changed behind the editor's back
            self._commit()
        self.cur = idx
        text = self.chapters[idx][1]
        self.editor.configure(state="normal")
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        tb = self.editor._textbox
        tb.edit_reset()
        tb.tag_remove("match", "1.0", "end")
        tb.mark_set("insert", "1.0")
        tb.see("1.0")
        if update_list:
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(idx)
            self.listbox.see(idx)

    def _commit_soon(self):
        if self._commit_job:
            self.after_cancel(self._commit_job)
        self._commit_job = self.after(400, self._commit)

    def _commit(self):
        """Copy the editor's text back into the working copy."""
        if self._commit_job:
            self.after_cancel(self._commit_job)
            self._commit_job = None
        if self.cur is None:
            return
        self.chapters[self.cur][1] = self.editor.get("1.0", "end-1c")
        self._refresh_item(self.cur)

    def _refresh_item(self, i):
        name, text = self.chapters[i]
        lab = ("● " if text != self.original[name] else "  ") + name
        if lab != self._labels[i]:
            self._labels[i] = lab
            sel = self.listbox.curselection()
            self.listbox.delete(i)
            self.listbox.insert(i, lab)
            for s in sel:
                self.listbox.selection_set(s)

    def _revert_chapter(self):
        if self.cur is None:
            return
        name = self.chapters[self.cur][0]
        self.chapters[self.cur][1] = self.original[name]
        self._refresh_item(self.cur)
        self._select(self.cur, commit=False)
        self._status(f"Reverted {name}")

    # =====================================================================
    # EDIT tab: find / replace
    # =====================================================================
    def _pattern(self):
        try:
            return editlib.compile_pattern(
                self.find_var.get(), self.case_var.get(), self.word_var.get(), self.regex_var.get())
        except ValueError as e:
            self._status(str(e))
            return None

    def _highlight(self, start, end):
        tb = self.editor._textbox
        a, b = f"1.0+{start}c", f"1.0+{end}c"
        tb.tag_remove("match", "1.0", "end")
        tb.tag_add("match", a, b)
        tb.mark_set("insert", b)
        tb.see(a)

    def _find_next(self):
        if self.cur is None:
            self._status("Open a book first.")
            return
        pat = self._pattern()
        if pat is None:
            return
        self._commit()
        n = len(self.chapters)
        start = len(self.editor._textbox.get("1.0", "insert"))
        for step in range(n + 1):  # last step wraps back to the start of this chapter
            idx = (self.cur + step) % n
            m = editlib.find_next(pat, self.chapters[idx][1], start if step == 0 else 0)
            if m:
                if idx != self.cur:
                    self._select(idx)
                self._highlight(m.start(), m.end())
                self._match = (idx, m.start(), m.end())
                total = sum(editlib.count_matches(pat, t) for _, t in self.chapters)
                self._status(f"{self.chapters[idx][0]}   ·   {total} match(es) in book")
                return
        self._match = None
        self._status("No matches.")

    def _replace_one(self):
        if self.cur is None:
            self._status("Open a book first.")
            return
        pat = self._pattern()
        if pat is None:
            return
        self._commit()
        if self._match and self._match[0] == self.cur:
            _, s, e = self._match
            try:
                rep = editlib.expand_one(pat, self.chapters[self.cur][1], s, e,
                                         self.repl_var.get(), self.regex_var.get())
            except ValueError as ex:
                self._status(str(ex))
                return
            if rep is not None:
                self.editor.delete(f"1.0+{s}c", f"1.0+{e}c")
                self.editor.insert(f"1.0+{s}c", rep)
                self.editor._textbox.tag_remove("match", "1.0", "end")
                self.editor._textbox.mark_set("insert", f"1.0+{s + len(rep)}c")
                self._match = None
                self._commit()
        self._find_next()

    def _replace_all(self, whole_book):
        if self.cur is None:
            self._status("Open a book first.")
            return
        pat = self._pattern()
        if pat is None:
            return
        self._commit()
        targets = range(len(self.chapters)) if whole_book else [self.cur]
        results = []
        try:  # compute everything first so a bad replacement changes nothing
            for i in targets:
                new, count = editlib.replace_all(
                    pat, self.chapters[i][1], self.repl_var.get(), self.regex_var.get())
                if count:
                    results.append((i, new, count))
        except ValueError as ex:
            self._status(str(ex))
            return
        if not results:
            self._status("No matches.")
            return
        for i, new, _ in results:
            self.chapters[i][1] = new
            self._refresh_item(i)
        top = self.editor._textbox.yview()[0]
        self._select(self.cur, commit=False)
        self.editor._textbox.yview_moveto(top)
        total = sum(c for _, _, c in results)
        self._status(f"Replaced {total} in {len(results)} chapter(s).")

    # =====================================================================
    # EDIT tab: export
    # =====================================================================
    def _export(self):
        if not self.chapters:
            self._status("Open a book first.")
            return
        self._commit()
        fmt = self.fmt_var.get()
        ext = {"EPUB": ".epub", "PDF": ".pdf", "TXT": ".txt"}[fmt]
        path = filedialog.asksaveasfilename(
            title=f"Export as {fmt}", defaultextension=ext,
            initialfile=f"{self.loaded_path.stem}_edited{ext}", filetypes=[(fmt, f"*{ext}")])
        if not path:
            return
        chapters = [(n, t) for n, t in self.chapters]
        fn = {"EPUB": exporters.export_epub, "PDF": exporters.export_pdf, "TXT": exporters.export_txt}[fmt]
        self._status(f"Exporting {fmt}...")
        self.update_idletasks()
        try:
            fn(chapters, path, title=self.loaded_path.stem)
            self._status(f"Exported {Path(path).name}")
        except Exception as e:
            self._status(f"Export failed: {e}")

    # =====================================================================
    # background-thread messages
    # =====================================================================
    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "progress":
                    self.bar.set(payload)
                elif kind == "done":
                    self.start_btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
                elif kind == "loaded":
                    self._on_loaded(*payload)
                elif kind == "edit_status":
                    self._status(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll)


if __name__ == "__main__":
    App().mainloop()
