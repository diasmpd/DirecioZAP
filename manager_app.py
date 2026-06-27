"""
DirecioZAP Manager
Interface grafica de gestao do bot de WhatsApp
"""

import os
import sys
import json
import time
import threading
import subprocess
import webbrowser
import requests
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

import customtkinter as ctk

# ── Ambiente ──────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

ENV_FILE = BASE_DIR / ".env"

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# ── Paleta ────────────────────────────────────────────────────
C_SIDEBAR       = "#1E293B"
C_SIDEBAR_BTN   = "#334155"
C_SIDEBAR_ACTIVE= "#2563EB"
C_BG            = "#F1F5F9"
C_CARD          = "#FFFFFF"
C_ACCENT        = "#2563EB"
C_TEXT          = "#1E293B"
C_MUTED         = "#64748B"
C_BORDER        = "#E2E8F0"
C_SUCCESS       = "#059669"
C_DANGER        = "#DC2626"

F_TITLE   = ("Segoe UI", 18, "bold")
F_SECTION = ("Segoe UI", 12, "bold")
F_BODY    = ("Segoe UI", 11)
F_SMALL   = ("Segoe UI", 10)
F_MONO    = ("Consolas", 10)

TIPOS_VALIDOS = ["texto", "cnpj", "email", "telefone", "contato", "estados"]


# ── EnvManager ────────────────────────────────────────────────
class EnvManager:
    def load(self) -> dict:
        result = {}
        if not ENV_FILE.exists():
            return result
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, _, v = s.partition("=")
                result[k.strip()] = v.strip()
        return result

    def save(self, updates: dict) -> None:
        lines = []
        written = set()

        if ENV_FILE.exists():
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#") and "=" in s:
                        k = s.split("=", 1)[0].strip()
                        if k in updates:
                            lines.append(f"{k}={updates[k]}\n")
                            written.add(k)
                        else:
                            lines.append(line if line.endswith("\n") else line + "\n")
                    else:
                        lines.append(line if line.endswith("\n") else line + "\n")

        for k, v in updates.items():
            if k not in written:
                lines.append(f"{k}={v}\n")

        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def get(self, key: str, default: str = "") -> str:
        return self.load().get(key, default)


env = EnvManager()


# ── SupabaseAPI ───────────────────────────────────────────────
class SupabaseAPI:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _get(self, table: str, params: str = "") -> list:
        r = requests.get(
            f"{self.url}/rest/v1/{table}?{params}",
            headers=self.headers, timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def _post(self, table: str, data: dict) -> dict:
        r = requests.post(
            f"{self.url}/rest/v1/{table}",
            headers=self.headers, json=data, timeout=10,
        )
        r.raise_for_status()
        res = r.json()
        return res[0] if isinstance(res, list) and res else res

    def _patch(self, table: str, flt: str, data: dict) -> None:
        r = requests.patch(
            f"{self.url}/rest/v1/{table}?{flt}",
            headers=self.headers, json=data, timeout=10,
        )
        r.raise_for_status()

    def _delete(self, table: str, flt: str) -> None:
        r = requests.delete(
            f"{self.url}/rest/v1/{table}?{flt}",
            headers=self.headers, timeout=10,
        )
        r.raise_for_status()

    def get_perguntas(self) -> list:
        return self._get("perguntas", "order=ordem&select=*")

    def create_pergunta(self, data: dict) -> dict:
        return self._post("perguntas", data)

    def update_pergunta(self, id_: int, data: dict) -> None:
        self._patch("perguntas", f"id=eq.{id_}", data)

    def delete_pergunta(self, id_: int) -> None:
        self._delete("perguntas", f"id=eq.{id_}")

    def get_sessions(self) -> list:
        return self._get("sessions", "order=atualizado_em.desc&limit=50&select=*")

    def get_cadastros(self) -> list:
        return self._get("cadastros", "order=criado_em.desc&limit=100&select=*")

    @staticmethod
    def from_env() -> "SupabaseAPI | None":
        cfg = env.load()
        url = cfg.get("SUPABASE_URL", "")
        key = cfg.get("SUPABASE_KEY", "")
        if not url or not key or "coloque_aqui" in url:
            return None
        return SupabaseAPI(url, key)


# ── BotController ─────────────────────────────────────────────
class UvicornServer:
    """Thin wrapper that allows stopping uvicorn from another thread."""
    def __init__(self, app, port: int):
        self._app = app
        self._port = port
        self._server = None

    def run(self):
        import uvicorn
        config = uvicorn.Config(
            self._app, host="0.0.0.0", port=self._port, log_level="error"
        )

        class _S(uvicorn.Server):
            def install_signal_handlers(self_):
                pass

        self._server = _S(config)
        self._server.run()

    def stop(self):
        if self._server:
            self._server.should_exit = True


class BotController:
    def __init__(self):
        self.running = False
        self.ngrok_url = ""
        self._wrapper = None
        self._ngrok_proc = None
        self._callback = None

    def set_callback(self, cb):
        self._callback = cb

    def _notify(self):
        if self._callback:
            self._callback()

    def start(self) -> str:
        if self.running:
            return "Bot ja esta em execucao."
        try:
            sys.path.insert(0, str(BASE_DIR))
            os.chdir(str(BASE_DIR))

            # Reload env so settings picks up saved values
            for k, v in env.load().items():
                os.environ.setdefault(k, v)
            # Force re-read
            for k, v in env.load().items():
                os.environ[k] = v

            from main import app as fastapi_app

            self._wrapper = UvicornServer(fastapi_app, 3000)
            t = threading.Thread(target=self._wrapper.run, daemon=True)
            t.start()
            time.sleep(1.5)

            self._start_ngrok()
            self.running = True
            self._notify()
            return "Bot iniciado com sucesso."
        except Exception as exc:
            return f"Erro ao iniciar bot: {exc}"

    def _start_ngrok(self):
        cfg = env.load()
        args = ["ngrok", "http", "3000"]
        domain = cfg.get("NGROK_DOMAIN", "").strip()
        if domain:
            args += ["--domain", domain]
        auth = cfg.get("NGROK_AUTH_TOKEN", "").strip()
        if auth and auth != "coloque_aqui":
            subprocess.run(["ngrok", "authtoken", auth],
                           capture_output=True, timeout=10)
        try:
            self._ngrok_proc = subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(2.5)
            r = requests.get("http://localhost:4040/api/tunnels", timeout=4)
            for t in r.json().get("tunnels", []):
                if t.get("proto") == "https":
                    self.ngrok_url = t["public_url"]
                    break
        except Exception:
            self.ngrok_url = "(ngrok indisponivel)"

    def stop(self):
        if self._wrapper:
            self._wrapper.stop()
            self._wrapper = None
        if self._ngrok_proc:
            self._ngrok_proc.terminate()
            self._ngrok_proc = None
        self.running = False
        self.ngrok_url = ""
        self._notify()


bot = BotController()


# ── Utilitarios de UI ─────────────────────────────────────────
def card_frame(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=8,
                        border_width=1, border_color=C_BORDER, **kw)


def section_label(parent, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=F_SECTION,
                        text_color=C_TEXT, anchor="w")


def field_label(parent, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=F_BODY,
                        text_color=C_TEXT, anchor="w")


def feedback_label(parent) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text="", font=F_SMALL,
                        text_color=C_SUCCESS, anchor="w")


def eye_button(parent, entry: ctk.CTkEntry) -> ctk.CTkButton:
    def toggle():
        if entry.cget("show") == "*":
            entry.configure(show="")
            btn.configure(text="Ocultar")
        else:
            entry.configure(show="*")
            btn.configure(text="Mostrar")
    btn = ctk.CTkButton(parent, text="Mostrar", width=70, height=28,
                        fg_color=C_BORDER, text_color=C_TEXT,
                        hover_color="#CBD5E1", command=toggle, font=F_SMALL)
    return btn


def treeview_style():
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("App.Treeview",
                    background=C_CARD,
                    foreground=C_TEXT,
                    rowheight=28,
                    fieldbackground=C_CARD,
                    borderwidth=0,
                    font=F_BODY)
    style.configure("App.Treeview.Heading",
                    background=C_BG,
                    foreground=C_MUTED,
                    font=("Segoe UI", 10, "bold"),
                    relief="flat")
    style.map("App.Treeview", background=[("selected", "#DBEAFE")])
    style.map("App.Treeview.Heading", background=[("active", C_BORDER)])


# ── PerguntaDialog ────────────────────────────────────────────
class PerguntaDialog(ctk.CTkToplevel):
    def __init__(self, parent, title: str, data: dict | None = None):
        super().__init__(parent)
        self.title(title)
        self.geometry("560x520")
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._build(data or {})

    def _build(self, d: dict):
        pad = {"padx": 24, "pady": 6}

        section_label(self, "Configuracao da Pergunta").pack(anchor="w", **pad, pady=(18, 4))

        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", **pad)

        field_label(row1, "Ordem").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.e_ordem = ctk.CTkEntry(row1, width=60)
        self.e_ordem.insert(0, str(d.get("ordem", 1)))
        self.e_ordem.grid(row=1, column=0, padx=(0, 16))

        field_label(row1, "Tipo de Validacao").grid(row=0, column=1, sticky="w")
        self.e_tipo = ctk.CTkOptionMenu(row1, values=TIPOS_VALIDOS, width=160)
        self.e_tipo.set(d.get("tipo", "texto"))
        self.e_tipo.grid(row=1, column=1)

        for label, attr, val in [
            ("Campo (snake_case, sem espacos)", "e_campo", d.get("campo", "")),
            ("Label (nome exibido no resumo)", "e_label", d.get("label", "")),
        ]:
            field_label(self, label).pack(anchor="w", **pad, pady=(8, 0))
            e = ctk.CTkEntry(self, width=480)
            e.insert(0, val)
            e.pack(anchor="w", **pad, pady=(0, 0))
            setattr(self, attr, e)

        field_label(self, "Texto da Pergunta").pack(anchor="w", **pad, pady=(8, 0))
        self.e_pergunta = ctk.CTkTextbox(self, width=480, height=72, font=F_BODY)
        self.e_pergunta.insert("1.0", d.get("pergunta", ""))
        self.e_pergunta.pack(anchor="w", **pad)

        field_label(self, "Mensagem de Erro (opcional)").pack(anchor="w", **pad, pady=(8, 0))
        self.e_msgerro = ctk.CTkEntry(self, width=480)
        self.e_msgerro.insert(0, d.get("msg_erro") or "")
        self.e_msgerro.pack(anchor="w", **pad)

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", **pad, pady=(12, 0))
        field_label(row2, "Ativo").pack(side="left", padx=(0, 10))
        self.sw_ativo = ctk.CTkSwitch(row2, text="")
        if d.get("ativo", True):
            self.sw_ativo.select()
        self.sw_ativo.pack(side="left")

        self.lbl_feedback = feedback_label(self)
        self.lbl_feedback.pack(anchor="w", padx=24)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(side="bottom", fill="x", padx=24, pady=16)
        ctk.CTkButton(btns, text="Cancelar", width=100,
                      fg_color=C_BORDER, text_color=C_TEXT,
                      hover_color="#CBD5E1",
                      command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btns, text="Salvar", width=100,
                      fg_color=C_ACCENT,
                      command=self._save).pack(side="right")

    def _save(self):
        campo = self.e_campo.get().strip().replace(" ", "_")
        label = self.e_label.get().strip()
        pergunta = self.e_pergunta.get("1.0", "end").strip()
        if not campo or not label or not pergunta:
            self.lbl_feedback.configure(text="Campo, Label e Pergunta sao obrigatorios.",
                                        text_color=C_DANGER)
            return
        try:
            ordem = int(self.e_ordem.get())
        except ValueError:
            self.lbl_feedback.configure(text="Ordem deve ser um numero inteiro.",
                                        text_color=C_DANGER)
            return
        self.result = {
            "ordem": ordem,
            "campo": campo,
            "label": label,
            "pergunta": pergunta,
            "tipo": self.e_tipo.get(),
            "msg_erro": self.e_msgerro.get().strip() or None,
            "ativo": bool(self.sw_ativo.get()),
        }
        self.destroy()


# ── Tab: Perguntas ────────────────────────────────────────────
class PerguntasTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C_BG)
        treeview_style()
        self._rows = []
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 8))
        ctk.CTkLabel(header, text="Perguntas do Formulario", font=F_TITLE,
                     text_color=C_TEXT).pack(side="left")

        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.pack(fill="x", padx=24, pady=(0, 8))

        def mk_btn(text, cmd, accent=False):
            return ctk.CTkButton(
                btn_bar, text=text, width=110, height=32,
                fg_color=C_ACCENT if accent else C_CARD,
                text_color="#FFFFFF" if accent else C_TEXT,
                hover_color="#1D4ED8" if accent else C_BORDER,
                border_width=0 if accent else 1,
                border_color=C_BORDER,
                font=F_SMALL, command=cmd,
            )

        mk_btn("Adicionar", self._add, accent=True).pack(side="left", padx=(0, 6))
        mk_btn("Editar", self._edit).pack(side="left", padx=(0, 6))
        mk_btn("Excluir", self._delete).pack(side="left", padx=(0, 6))
        mk_btn("Mover Acima", self._move_up).pack(side="left", padx=(0, 6))
        mk_btn("Mover Abaixo", self._move_down).pack(side="left", padx=(0, 6))
        mk_btn("Atualizar", self._load).pack(side="right")

        self.lbl_status = ctk.CTkLabel(self, text="", font=F_SMALL,
                                       text_color=C_MUTED)
        self.lbl_status.pack(anchor="w", padx=24, pady=(0, 4))

        tree_frame = card_frame(self)
        tree_frame.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        cols = ("ordem", "campo", "label", "pergunta", "tipo", "ativo")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                  style="App.Treeview", selectmode="browse")

        widths = {"ordem": 55, "campo": 130, "label": 120,
                  "pergunta": 280, "tipo": 90, "ativo": 55}
        heads = {"ordem": "Ordem", "campo": "Campo", "label": "Label",
                 "pergunta": "Pergunta", "tipo": "Tipo", "ativo": "Ativo"}
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c], minwidth=40,
                             anchor="center" if c in ("ordem", "tipo", "ativo") else "w")

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y", pady=4)

        self._load()

    def _supabase(self) -> SupabaseAPI | None:
        sb = SupabaseAPI.from_env()
        if not sb:
            self.lbl_status.configure(
                text="Supabase nao configurado. Vá em Configuracoes e salve as credenciais.",
                text_color=C_DANGER)
        return sb

    def _load(self):
        sb = self._supabase()
        if not sb:
            return
        self.lbl_status.configure(text="Carregando...", text_color=C_MUTED)
        self.update()
        try:
            self._rows = sb.get_perguntas()
            self.tree.delete(*self.tree.get_children())
            for r in self._rows:
                self.tree.insert("", "end", iid=str(r["id"]), values=(
                    r.get("ordem", ""),
                    r.get("campo", ""),
                    r.get("label", ""),
                    r.get("pergunta", "")[:60] + ("..." if len(r.get("pergunta","")) > 60 else ""),
                    r.get("tipo", ""),
                    "Sim" if r.get("ativo", True) else "Nao",
                ))
            self.lbl_status.configure(
                text=f"{len(self._rows)} pergunta(s) carregada(s).",
                text_color=C_SUCCESS)
        except Exception as ex:
            self.lbl_status.configure(text=f"Erro: {ex}", text_color=C_DANGER)

    def _selected_row(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        rid = int(sel[0])
        return next((r for r in self._rows if r["id"] == rid), None)

    def _add(self):
        dlg = PerguntaDialog(self, "Adicionar Pergunta")
        self.wait_window(dlg)
        if not dlg.result:
            return
        sb = self._supabase()
        if not sb:
            return
        try:
            sb.create_pergunta(dlg.result)
            self._load()
        except Exception as ex:
            messagebox.showerror("Erro", str(ex))

    def _edit(self):
        row = self._selected_row()
        if not row:
            messagebox.showinfo("Aviso", "Selecione uma pergunta para editar.")
            return
        dlg = PerguntaDialog(self, "Editar Pergunta", row)
        self.wait_window(dlg)
        if not dlg.result:
            return
        sb = self._supabase()
        if not sb:
            return
        try:
            sb.update_pergunta(row["id"], dlg.result)
            self._load()
        except Exception as ex:
            messagebox.showerror("Erro", str(ex))

    def _delete(self):
        row = self._selected_row()
        if not row:
            messagebox.showinfo("Aviso", "Selecione uma pergunta para excluir.")
            return
        if not messagebox.askyesno("Confirmar",
                                    f"Excluir a pergunta '{row['label']}'?"):
            return
        sb = self._supabase()
        if not sb:
            return
        try:
            sb.delete_pergunta(row["id"])
            self._load()
        except Exception as ex:
            messagebox.showerror("Erro", str(ex))

    def _move(self, direction: int):
        row = self._selected_row()
        if not row:
            return
        sb = self._supabase()
        if not sb:
            return
        ordered = sorted(self._rows, key=lambda r: r["ordem"])
        idx = next((i for i, r in enumerate(ordered) if r["id"] == row["id"]), -1)
        swap_idx = idx + direction
        if swap_idx < 0 or swap_idx >= len(ordered):
            return
        a, b = ordered[idx], ordered[swap_idx]
        try:
            sb.update_pergunta(a["id"], {"ordem": b["ordem"]})
            sb.update_pergunta(b["id"], {"ordem": a["ordem"]})
            self._load()
        except Exception as ex:
            messagebox.showerror("Erro", str(ex))

    def _move_up(self): self._move(-1)
    def _move_down(self): self._move(1)


# ── Tab: Mensagens ────────────────────────────────────────────
class MensagensTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C_BG)
        treeview_style()
        self._view = "sessions"
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 8))
        ctk.CTkLabel(header, text="Monitoramento de Mensagens", font=F_TITLE,
                     text_color=C_TEXT).pack(side="left")

        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=24, pady=(0, 8))

        self.seg = ctk.CTkSegmentedButton(
            ctrl, values=["Sessoes Ativas", "Cadastros Concluidos"],
            command=self._switch_view, font=F_BODY,
        )
        self.seg.set("Sessoes Ativas")
        self.seg.pack(side="left")

        ctk.CTkButton(ctrl, text="Atualizar", width=100, height=32,
                      fg_color=C_CARD, text_color=C_TEXT,
                      hover_color=C_BORDER, border_width=1,
                      border_color=C_BORDER, font=F_SMALL,
                      command=self._load).pack(side="right", padx=(6, 0))

        ctk.CTkButton(ctrl, text="Baixar Excel", width=110, height=32,
                      fg_color=C_ACCENT, font=F_SMALL,
                      command=self._download_excel).pack(side="right")

        self.lbl_count = ctk.CTkLabel(self, text="", font=F_SMALL,
                                       text_color=C_MUTED)
        self.lbl_count.pack(anchor="w", padx=24, pady=(0, 4))

        tree_frame = card_frame(self)
        tree_frame.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        self.tree = ttk.Treeview(tree_frame, show="headings",
                                  style="App.Treeview", selectmode="browse")
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y", pady=4)

        self._setup_sessions_cols()
        self._load()

    def _setup_sessions_cols(self):
        cols = ("phone", "state", "updated")
        self.tree.configure(columns=cols)
        self.tree.heading("phone", text="Telefone")
        self.tree.heading("state", text="Estado da Conversa")
        self.tree.heading("updated", text="Ultima Atualizacao")
        self.tree.column("phone", width=160)
        self.tree.column("state", width=220)
        self.tree.column("updated", width=200)

    def _setup_cadastros_cols(self):
        cols = ("phone", "dados", "created")
        self.tree.configure(columns=cols)
        self.tree.heading("phone", text="Telefone")
        self.tree.heading("dados", text="Resumo dos Dados")
        self.tree.heading("created", text="Data do Cadastro")
        self.tree.column("phone", width=160)
        self.tree.column("dados", width=400)
        self.tree.column("created", width=200)

    def _switch_view(self, val: str):
        self._view = "sessions" if val == "Sessoes Ativas" else "cadastros"
        self.tree.delete(*self.tree.get_children())
        if self._view == "sessions":
            self._setup_sessions_cols()
        else:
            self._setup_cadastros_cols()
        self._load()

    def _load(self):
        sb = SupabaseAPI.from_env()
        if not sb:
            self.lbl_count.configure(
                text="Supabase nao configurado.", text_color=C_DANGER)
            return
        try:
            self.tree.delete(*self.tree.get_children())
            if self._view == "sessions":
                data = sb.get_sessions()
                for r in data:
                    self.tree.insert("", "end", values=(
                        r.get("phone", ""),
                        r.get("state", ""),
                        r.get("atualizado_em", "")[:19].replace("T", " "),
                    ))
                self.lbl_count.configure(
                    text=f"{len(data)} sessao(oes) ativa(s).",
                    text_color=C_MUTED)
            else:
                data = sb.get_cadastros()
                for r in data:
                    dados = r.get("dados", {})
                    resumo = " | ".join(f"{k}: {v}" for k, v in list(dados.items())[:3])
                    self.tree.insert("", "end", values=(
                        r.get("phone", ""),
                        resumo,
                        r.get("criado_em", "")[:19].replace("T", " "),
                    ))
                self.lbl_count.configure(
                    text=f"{len(data)} cadastro(s) concluido(s).",
                    text_color=C_MUTED)
        except Exception as ex:
            self.lbl_count.configure(text=f"Erro: {ex}", text_color=C_DANGER)

    def _download_excel(self):
        token = env.get("VERIFY_TOKEN", "")
        if not token:
            messagebox.showerror("Erro", "VERIFY_TOKEN nao configurado.")
            return
        dest = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Planilha Excel", "*.xlsx")],
            initialfile="cadastros_direciozap.xlsx",
        )
        if not dest:
            return
        try:
            r = requests.get(
                f"http://localhost:3000/exportar?token={token}", timeout=10
            )
            if r.status_code == 404:
                messagebox.showinfo("Aviso", "Nenhum cadastro salvo ainda.")
                return
            r.raise_for_status()
            with open(dest, "wb") as f:
                f.write(r.content)
            messagebox.showinfo("Sucesso", f"Arquivo salvo em:\n{dest}")
        except requests.ConnectionError:
            messagebox.showerror("Erro", "Bot nao esta em execucao. Inicie o bot primeiro.")
        except Exception as ex:
            messagebox.showerror("Erro", str(ex))


# ── Tab: Configuracoes ────────────────────────────────────────
class ConfiguracoesTab(ctk.CTkScrollableFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C_BG, scrollbar_button_color=C_BORDER)
        self._build()
        self._load_values()

    def _card(self, title: str) -> ctk.CTkFrame:
        f = card_frame(self)
        f.pack(fill="x", padx=24, pady=(0, 16))
        section_label(f, title).pack(anchor="w", padx=16, pady=(14, 8))
        return f

    def _field(self, parent, label: str, secret=False) -> tuple[ctk.CTkEntry, ctk.CTkButton | None]:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 10))
        field_label(row, label).pack(anchor="w")
        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x")
        e = ctk.CTkEntry(inner, height=34, show="*" if secret else "",
                         font=F_BODY, border_color=C_BORDER)
        e.pack(side="left", fill="x", expand=True)
        btn = None
        if secret:
            btn = eye_button(inner, e)
            btn.pack(side="left", padx=(6, 0))
        return e, btn

    def _build(self):
        ctk.CTkLabel(self, text="Configuracoes", font=F_TITLE,
                     text_color=C_TEXT).pack(anchor="w", padx=24, pady=(20, 16))

        # Provedor
        c_prov = self._card("Provedor WhatsApp")
        self.seg_prov = ctk.CTkSegmentedButton(
            c_prov, values=["Twilio", "Meta"],
            command=self._toggle_provider, font=F_BODY,
        )
        self.seg_prov.set("Twilio")
        self.seg_prov.pack(anchor="w", padx=16, pady=(0, 14))

        # Twilio
        self.card_twilio = self._card("Twilio")
        self.e_twilio_sid, _ = self._field(self.card_twilio, "Account SID")
        self.e_twilio_token, _ = self._field(self.card_twilio, "Auth Token", secret=True)
        self.e_twilio_from, _ = self._field(self.card_twilio, "Numero do Sandbox (ex: +14155238886)")

        twilio_row = ctk.CTkFrame(self.card_twilio, fg_color="transparent")
        twilio_row.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(twilio_row, text="Acessar Sandbox Twilio", width=200, height=32,
                      fg_color=C_ACCENT, font=F_SMALL,
                      command=lambda: webbrowser.open(
                          "https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn"
                      )).pack(side="left")
        ctk.CTkLabel(twilio_row,
                     text="  O usuario deve enviar 'join [palavra]' para +1 415 523 8886",
                     font=F_SMALL, text_color=C_MUTED).pack(side="left")

        # Meta
        self.card_meta = self._card("Meta WhatsApp Cloud API")
        self.e_meta_phone_id, _ = self._field(self.card_meta, "Phone Number ID")
        self.e_meta_token, _ = self._field(self.card_meta, "Access Token", secret=True)
        self.e_meta_verify, _ = self._field(self.card_meta, "Verify Token")

        meta_row = ctk.CTkFrame(self.card_meta, fg_color="transparent")
        meta_row.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(meta_row, text="Acessar Meta Developers", width=200, height=32,
                      fg_color="#1877F2", font=F_SMALL,
                      command=lambda: webbrowser.open("https://developers.facebook.com")).pack(side="left")
        ctk.CTkLabel(meta_row,
                     text="  Limitacao: sandbox nao envia para numeros brasileiros (+55)",
                     font=F_SMALL, text_color=C_DANGER).pack(side="left")

        # ngrok
        c_ng = self._card("ngrok (tunelamento publico)")
        self.e_ngrok_token, _ = self._field(c_ng, "Auth Token do ngrok (opcional)")
        self.e_ngrok_domain, _ = self._field(c_ng, "Dominio estatico (opcional, ex: abc.ngrok-free.app)")
        ctk.CTkLabel(c_ng,
                     text="Instale ngrok em ngrok.com/download  |  Configure com: ngrok authtoken SEU_TOKEN",
                     font=F_SMALL, text_color=C_MUTED).pack(anchor="w", padx=16, pady=(0, 14))

        # Supabase
        c_sb = self._card("Supabase")
        self.e_sb_url, _ = self._field(c_sb, "Project URL (ex: https://xxxxx.supabase.co)")
        self.e_sb_key, _ = self._field(c_sb, "API Key (anon public)", secret=True)

        sb_row = ctk.CTkFrame(c_sb, fg_color="transparent")
        sb_row.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(sb_row, text="Testar Conexao", width=140, height=32,
                      fg_color=C_CARD, text_color=C_TEXT,
                      hover_color=C_BORDER, border_width=1, border_color=C_BORDER,
                      font=F_SMALL, command=self._test_supabase).pack(side="left")
        self.lbl_sb_test = ctk.CTkLabel(sb_row, text="", font=F_SMALL,
                                         text_color=C_MUTED)
        self.lbl_sb_test.pack(side="left", padx=10)

        # Verify Token
        c_vt = self._card("Token de Seguranca")
        self.e_verify, _ = self._field(c_vt, "Verify Token (protege o endpoint /exportar)")
        ctk.CTkLabel(c_vt, text="Gere qualquer string segura. Ex: use um UUID.",
                     font=F_SMALL, text_color=C_MUTED).pack(anchor="w", padx=16, pady=(0, 14))

        self.lbl_save = feedback_label(self)
        self.lbl_save.pack(anchor="w", padx=24, pady=(0, 4))

        ctk.CTkButton(self, text="Salvar Configuracoes", height=40,
                      fg_color=C_ACCENT, font=F_SECTION,
                      command=self._save).pack(fill="x", padx=24, pady=(0, 24))

        self._toggle_provider("Twilio")

    def _toggle_provider(self, val: str):
        if val == "Twilio":
            self.card_twilio.pack(fill="x", padx=24, pady=(0, 16))
            self.card_meta.pack_forget()
        else:
            self.card_meta.pack(fill="x", padx=24, pady=(0, 16))
            self.card_twilio.pack_forget()

    def _load_values(self):
        cfg = env.load()
        prov = cfg.get("WHATSAPP_PROVIDER", "Twilio")
        self.seg_prov.set(prov)
        self._toggle_provider(prov)

        mapping = {
            "TWILIO_ACCOUNT_SID": self.e_twilio_sid,
            "TWILIO_AUTH_TOKEN": self.e_twilio_token,
            "TWILIO_WHATSAPP_FROM": self.e_twilio_from,
            "META_PHONE_NUMBER_ID": self.e_meta_phone_id,
            "META_TOKEN": self.e_meta_token,
            "META_VERIFY_TOKEN": self.e_meta_verify,
            "NGROK_AUTH_TOKEN": self.e_ngrok_token,
            "NGROK_DOMAIN": self.e_ngrok_domain,
            "SUPABASE_URL": self.e_sb_url,
            "SUPABASE_KEY": self.e_sb_key,
            "VERIFY_TOKEN": self.e_verify,
        }
        for key, entry in mapping.items():
            val = cfg.get(key, "")
            if val:
                entry.delete(0, "end")
                entry.insert(0, val)

    def _save(self):
        prov = self.seg_prov.get()
        updates = {
            "WHATSAPP_PROVIDER": prov,
            "TWILIO_ACCOUNT_SID": self.e_twilio_sid.get().strip(),
            "TWILIO_AUTH_TOKEN": self.e_twilio_token.get().strip(),
            "TWILIO_WHATSAPP_FROM": self.e_twilio_from.get().strip(),
            "META_PHONE_NUMBER_ID": self.e_meta_phone_id.get().strip(),
            "META_TOKEN": self.e_meta_token.get().strip(),
            "META_VERIFY_TOKEN": self.e_meta_verify.get().strip(),
            "NGROK_AUTH_TOKEN": self.e_ngrok_token.get().strip(),
            "NGROK_DOMAIN": self.e_ngrok_domain.get().strip(),
            "SUPABASE_URL": self.e_sb_url.get().strip(),
            "SUPABASE_KEY": self.e_sb_key.get().strip(),
            "VERIFY_TOKEN": self.e_verify.get().strip(),
        }
        updates = {k: v for k, v in updates.items() if v}
        env.save(updates)
        self.lbl_save.configure(text="Configuracoes salvas com sucesso.", text_color=C_SUCCESS)
        self.after(3000, lambda: self.lbl_save.configure(text=""))

    def _test_supabase(self):
        url = self.e_sb_url.get().strip()
        key = self.e_sb_key.get().strip()
        if not url or not key:
            self.lbl_sb_test.configure(text="Preencha URL e Key antes de testar.", text_color=C_DANGER)
            return
        self.lbl_sb_test.configure(text="Testando...", text_color=C_MUTED)
        self.update()
        try:
            api = SupabaseAPI(url, key)
            api.get_perguntas()
            self.lbl_sb_test.configure(text="Conexao OK", text_color=C_SUCCESS)
        except Exception as ex:
            self.lbl_sb_test.configure(text=f"Falhou: {ex}", text_color=C_DANGER)


# ── Tab: Tutorial ─────────────────────────────────────────────
TUTORIAL_TEXT = [
    ("SOBRE O DIRECIOZAP", True),
    ("O DirecioZAP e um bot de WhatsApp que coleta informacoes de usuarios via conversa automatizada. "
     "O administrador configura as perguntas, e os usuarios respondem naturalmente pelo WhatsApp. "
     "Os dados sao salvos no Supabase e exportaveis em Excel.\n", False),

    ("1. CONFIGURANDO O SUPABASE", True),
    ("1.1  Acesse supabase.com e crie uma conta gratuita.", False),
    ("1.2  Clique em 'New Project', defina um nome e senha.", False),
    ("1.3  No menu lateral, acesse SQL Editor e execute:\n", False),
    ("""CREATE TABLE perguntas (
  id        SERIAL PRIMARY KEY,
  ordem     INTEGER NOT NULL,
  campo     TEXT NOT NULL UNIQUE,
  label     TEXT NOT NULL,
  pergunta  TEXT NOT NULL,
  tipo      TEXT NOT NULL DEFAULT 'texto',
  msg_erro  TEXT,
  ativo     BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO perguntas (ordem, campo, label, pergunta, tipo, msg_erro) VALUES
  (1,'razao_social','Razao Social','Qual e a Razao Social da sua empresa?','texto',NULL),
  (2,'cnpj','CNPJ','Informe o CNPJ da empresa:','cnpj','CNPJ invalido.'),
  (3,'contato','Contato','Qual o contato principal? (telefone ou e-mail):','contato','Formato invalido.'),
  (4,'servico','Servico','Que tipo de servico sua empresa oferece?','texto',NULL),
  (5,'estados','Estados','Em quais estados atuam? (ex: MG, SP):','estados','Siglas invalidas.');

CREATE TABLE cadastros (
  id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone     TEXT NOT NULL,
  dados     JSONB NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE sessions (
  phone         TEXT PRIMARY KEY,
  state         TEXT NOT NULL DEFAULT 'SAUDACAO',
  dados         JSONB NOT NULL DEFAULT '{}',
  tentativas    JSONB NOT NULL DEFAULT '{}',
  criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);\n""", False),
    ("1.4  Em Project Settings > API, copie a Project URL e a chave 'anon public'.", False),
    ("1.5  Cole as credenciais na aba Configuracoes deste aplicativo.\n", False),

    ("2. CONFIGURANDO O TWILIO (SANDBOX PARA TESTES)", True),
    ("2.1  Acesse twilio.com e crie uma conta gratuita.", False),
    ("2.2  No console, va em Messaging > Try it out > Send a WhatsApp message.", False),
    ("2.3  Copie o Account SID e o Auth Token da pagina inicial do console.", False),
    ("2.4  O numero do sandbox e +1 415 523 8886.", False),
    ("2.5  Na mesma pagina, em 'Sandbox Settings', configure o campo", False),
    ("     'When a message comes in' com a URL do ngrok + /webhook.", False),
    ("     Exemplo: https://abc123.ngrok-free.app/webhook", False),
    ("2.6  Para cada usuario que quiser usar o bot, ele deve enviar", False),
    ("     'join [palavra-do-sandbox]' para +1 415 523 8886 no WhatsApp.", False),
    ("     A palavra e mostrada no painel Twilio (ex: join yellow-tiger).", False),
    ("2.7  Apos 72h de inatividade, o usuario precisa fazer o join novamente.\n", False),

    ("3. CONFIGURANDO O META (PARA PRODUCAO)", True),
    ("3.1  Acesse developers.facebook.com e crie uma conta.", False),
    ("3.2  Crie um novo app do tipo 'Business'.", False),
    ("3.3  Adicione o produto 'WhatsApp' ao app.", False),
    ("3.4  Em API Setup, copie o Phone Number ID e gere o Access Token.", False),
    ("3.5  Em Configuration > Webhook, adicione a URL do ngrok + /webhook", False),
    ("     e o Verify Token configurado neste aplicativo.", False),
    ("3.6  Assine o campo 'messages' no webhook.", False),
    ("ATENCAO: o sandbox Meta nao envia mensagens para numeros brasileiros (+55).", False),
    ("Para producao com Brasil, e necessario verificar o negocio na Meta (processo de aprovacao).\n", False),

    ("4. CONFIGURANDO O NGROK", True),
    ("4.1  Acesse ngrok.com/download e baixe o executavel para Windows.", False),
    ("4.2  Crie uma conta gratuita em ngrok.com.", False),
    ("4.3  No painel ngrok, copie o Auth Token e cole em Configuracoes > ngrok.", False),
    ("4.4  Ao iniciar o bot neste aplicativo, o ngrok sobe automaticamente.", False),
    ("4.5  A URL publica aparece na barra lateral apos o bot iniciar.", False),
    ("4.6  Com conta gratuita, voce pode ter um dominio estatico (sem mudanca de URL).", False),
    ("     Configure em ngrok.com/dashboard > Domains e cole em 'Dominio Estatico'.\n", False),

    ("5. PERSONALIZANDO AS PERGUNTAS", True),
    ("5.1  Va para a aba 'Perguntas' e clique em 'Adicionar'.", False),
    ("5.2  Defina os campos:", False),
    ("     - Campo: identificador interno, sem espacos (ex: nome_empresa)", False),
    ("     - Label: nome exibido no resumo final (ex: Nome da Empresa)", False),
    ("     - Pergunta: texto que o bot envia ao usuario", False),
    ("     - Tipo: define como a resposta sera validada", False),
    ("     - Mensagem de Erro: texto enviado quando a resposta e invalida", False),
    ("5.3  Tipos de validacao disponíveis:", False),
    ("     texto    - qualquer texto nao vazio", False),
    ("     cnpj     - valida CNPJ com digitos verificadores", False),
    ("     email    - valida formato de e-mail", False),
    ("     telefone - valida numero de telefone brasileiro", False),
    ("     contato  - aceita e-mail ou telefone", False),
    ("     estados  - aceita siglas de estados brasileiros (MG, SP, RJ...)", False),
    ("5.4  Use 'Mover Acima / Mover Abaixo' para reordenar as perguntas.", False),
    ("5.5  Desative uma pergunta temporariamente com o campo 'Ativo = Nao'.\n", False),

    ("6. COMO O USUARIO USA O BOT", True),
    ("6.1  O usuario envia qualquer mensagem para o numero do bot.", False),
    ("6.2  O bot responde com a saudacao e a primeira pergunta.", False),
    ("6.3  O usuario responde cada pergunta em sequencia.", False),
    ("6.4  Apos a ultima pergunta, o bot exibe um resumo e pede confirmacao (S/N).", False),
    ("6.5  Ao confirmar, o cadastro e salvo no Supabase e no Excel.", False),
    ("6.6  Se o usuario errar 3 vezes a mesma pergunta, a sessao e encerrada.", False),
    ("6.7  Sessions expiram apos 24 horas sem interacao.\n", False),

    ("7. MONITORANDO AS RESPOSTAS", True),
    ("7.1  Na aba 'Mensagens', visualize todas as conversas.", False),
    ("7.2  'Sessoes Ativas': usuarios em conversa mas que ainda nao concluiram.", False),
    ("7.3  'Cadastros Concluidos': formularios finalizados e confirmados.", False),
    ("7.4  Clique em 'Baixar Excel' para exportar todos os cadastros.", False),
    ("     O bot precisa estar em execucao para o download funcionar.\n", False),
]


class TutorialTab(ctk.CTkScrollableFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C_BG, scrollbar_button_color=C_BORDER)
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Tutorial e Documentacao", font=F_TITLE,
                     text_color=C_TEXT).pack(anchor="w", padx=24, pady=(20, 16))

        content = card_frame(self)
        content.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        for text, is_title in TUTORIAL_TEXT:
            if is_title:
                ctk.CTkLabel(content, text=text,
                             font=("Segoe UI", 12, "bold"),
                             text_color=C_ACCENT, anchor="w",
                             justify="left").pack(
                    anchor="w", padx=20, pady=(16, 4))
            else:
                if text.startswith("CREATE ") or text.startswith("INSERT "):
                    ctk.CTkTextbox(content, height=320, font=F_MONO,
                                   fg_color="#F8FAFC", border_color=C_BORDER,
                                   border_width=1, wrap="none",
                                   state="normal").pack(
                        fill="x", padx=20, pady=(0, 8))
                    # Insert and then disable
                    boxes = [w for w in content.winfo_children()
                             if isinstance(w, ctk.CTkTextbox)]
                    boxes[-1].insert("1.0", text)
                    boxes[-1].configure(state="disabled")
                else:
                    ctk.CTkLabel(content, text=text,
                                 font=F_BODY, text_color=C_TEXT,
                                 anchor="w", justify="left",
                                 wraplength=820).pack(
                        anchor="w", padx=20, pady=(0, 2))


# ── App principal ─────────────────────────────────────────────
class DirecioZAPApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DirecioZAP Manager")
        self.geometry("1280x720")
        self.minsize(1024, 600)
        self.configure(fg_color=C_BG)

        bot.set_callback(self._update_bot_status)
        self._active_tab = None
        self._nav_btns = {}

        self._build()
        self._show("perguntas")

    def _build(self):
        # Sidebar
        self.sidebar = ctk.CTkFrame(self, fg_color=C_SIDEBAR,
                                     width=220, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        ctk.CTkLabel(self.sidebar, text="DirecioZAP",
                     font=("Segoe UI", 18, "bold"),
                     text_color="#F8FAFC").pack(pady=(28, 2))
        ctk.CTkLabel(self.sidebar, text="v1.0",
                     font=F_SMALL, text_color="#94A3B8").pack(pady=(0, 24))

        # Nav buttons
        nav_items = [
            ("perguntas", "Perguntas"),
            ("mensagens", "Mensagens"),
            ("configuracoes", "Configuracoes"),
            ("tutorial", "Tutorial"),
        ]
        for key, label in nav_items:
            btn = ctk.CTkButton(
                self.sidebar, text=label, anchor="w",
                height=40, corner_radius=6,
                fg_color="transparent",
                hover_color=C_SIDEBAR_BTN,
                text_color="#CBD5E1",
                font=F_BODY,
                command=lambda k=key: self._show(k),
            )
            btn.pack(fill="x", padx=12, pady=2)
            self._nav_btns[key] = btn

        # Separator
        ctk.CTkFrame(self.sidebar, height=1, fg_color="#334155").pack(
            fill="x", padx=12, pady=16)

        # Bot status
        self.dot = ctk.CTkLabel(self.sidebar, text="   Parado",
                                 font=F_SMALL, text_color="#EF4444")
        self.dot.pack(anchor="w", padx=16, pady=(0, 6))

        self.btn_bot = ctk.CTkButton(
            self.sidebar, text="Iniciar Bot", height=36,
            fg_color=C_SUCCESS, hover_color="#047857",
            font=F_BODY, command=self._toggle_bot,
        )
        self.btn_bot.pack(fill="x", padx=12, pady=(0, 8))

        self.lbl_ngrok = ctk.CTkLabel(
            self.sidebar, text="", font=F_SMALL,
            text_color="#94A3B8", wraplength=190, cursor="hand2",
        )
        self.lbl_ngrok.pack(padx=12, pady=(0, 8))
        self.lbl_ngrok.bind("<Button-1>", lambda e: self._open_ngrok())

        # Content area
        self.content = ctk.CTkFrame(self, fg_color=C_BG, corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)

        self._tabs = {
            "perguntas":      PerguntasTab(self.content),
            "mensagens":      MensagensTab(self.content),
            "configuracoes":  ConfiguracoesTab(self.content),
            "tutorial":       TutorialTab(self.content),
        }

    def _show(self, key: str):
        if self._active_tab:
            self._tabs[self._active_tab].pack_forget()
            self._nav_btns[self._active_tab].configure(
                fg_color="transparent", text_color="#CBD5E1")

        self._active_tab = key
        self._tabs[key].pack(fill="both", expand=True)
        self._nav_btns[key].configure(
            fg_color=C_SIDEBAR_ACTIVE, text_color="#FFFFFF")

    def _toggle_bot(self):
        if bot.running:
            bot.stop()
        else:
            self.btn_bot.configure(text="Iniciando...", state="disabled")
            self.update()
            msg = bot.start()
            self.btn_bot.configure(state="normal")
            if "Erro" in msg:
                messagebox.showerror("Erro ao iniciar bot", msg)

    def _update_bot_status(self):
        if bot.running:
            self.dot.configure(text="   Em execucao", text_color=C_SUCCESS)
            self.btn_bot.configure(text="Parar Bot", fg_color=C_DANGER,
                                    hover_color="#B91C1C")
            url = bot.ngrok_url
            if url and "indisponivel" not in url:
                self.lbl_ngrok.configure(text=url)
            else:
                self.lbl_ngrok.configure(text=url or "")
        else:
            self.dot.configure(text="   Parado", text_color="#EF4444")
            self.btn_bot.configure(text="Iniciar Bot", fg_color=C_SUCCESS,
                                    hover_color="#047857")
            self.lbl_ngrok.configure(text="")

    def _open_ngrok(self):
        url = bot.ngrok_url
        if url and url.startswith("http"):
            webbrowser.open(url)


def main():
    app = DirecioZAPApp()
    app.mainloop()


if __name__ == "__main__":
    main()
