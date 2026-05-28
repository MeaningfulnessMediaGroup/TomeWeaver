"""Tkinter prose lint overlays for text widgets and choice entries.

Wires offline spell check (red), grammar lint (amber), optional WordNet synonyms,
and optional LLM suggestions into right-click context menus. Scanning is debounced
and runs on a worker thread; UI updates are marshalled back via ``host.after``.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

from grammar_lint import GRAMMAR_ERROR_TAG, grammar_issue_at_offset
from spell_ai import extract_local_context, fetch_ai_word_suggestions, spell_ai_enabled
from spell_check import (
    SPELL_ERROR_TAG,
    SpellCheckService,
    char_offset_to_index,
    index_to_char_offset,
    word_at_entry_index,
    word_at_index,
)
from synonyms import fetch_synonyms, synonyms_enabled


def _lexicon_scope():
    """Normalized ``custom_dictionary_scope`` for menu labels."""
    from config import ENGINE_CONFIG

    scope = (ENGINE_CONFIG.get("custom_dictionary_scope") or "story").strip().lower()
    if scope not in ("global", "universe", "story"):
        scope = "story"
    return scope


def _dictionary_add_label(word):
    """Right-click label for Add to dictionary."""
    return f'Add "{word}" to {_lexicon_scope()} dictionary'


def _ignore_label(word):
    """Right-click label for spelling ignore."""
    return f'Ignore "{word}" ({_lexicon_scope()} list)'


def _ignore_grammar_label():
    """Right-click label for grammar ignore."""
    return f"Ignore this issue ({_lexicon_scope()} list)"


def _append_ai_suggest_item(menu, command):
    """Add optional **Get AI suggestions…** row when enabled in settings."""
    if spell_ai_enabled():
        menu.add_separator()
        menu.add_command(label="Get AI suggestions…", command=command)


def _append_synonyms_cascade(menu, word, replace_fn):
    """Add optional **Synonyms** submenu (lazy WordNet lookup)."""
    if not synonyms_enabled():
        return
    syns = fetch_synonyms(word)
    if not syns:
        return
    sub = tk.Menu(menu, tearoff=0)
    for syn in syns:
        sub.add_command(label=syn, command=lambda s=syn: replace_fn(s))
    menu.add_separator()
    menu.add_cascade(label="Synonyms", menu=sub)


def _popup_menu(menu, event):
    """Show a context menu at the pointer and release the grab on close."""
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def _locale_for_engine(engine):
    """Spelling locale string for AI suggestion prompts."""
    from config import ENGINE_CONFIG

    return (ENGINE_CONFIG.get("spelling_locale") or "american").strip().lower()


class _SpellAiMixin:
    """Shared async LLM suggestion flow for spell/grammar menus."""

    def _ai_blocked_reason(self):
        engine = self.get_engine()
        if engine is None:
            return "No active story engine."
        if getattr(engine, "is_test_mode", False):
            return "AI suggestions are disabled in test mode."
        if not spell_ai_enabled():
            return "Enable AI suggestions in Prose Lint Settings."
        from config import ENGINE_CONFIG

        if not (ENGINE_CONFIG.get("api_url") or "").strip():
            return "No LLM API configured. Set an active profile in Dashboard → Settings."
        return None

    def _request_ai_suggestions(self, event, word, context, issue_hint, apply_fn):
        blocked = self._ai_blocked_reason()
        if blocked:
            messagebox.showwarning("AI suggestions", blocked, parent=self.host)
            return

        engine = self.get_engine()
        adv_dir = getattr(engine, "adv_dir", None)
        locale = _locale_for_engine(engine)
        root = self.host.winfo_toplevel()
        try:
            root.configure(cursor="watch")
        except Exception:
            pass

        def worker():
            ok, result = fetch_ai_word_suggestions(
                word,
                context,
                locale=locale,
                issue_hint=issue_hint,
                adv_dir=adv_dir,
            )
            self.host.after(
                0,
                lambda: self._show_ai_results(event, ok, result, apply_fn, root),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _show_ai_results(self, event, ok, result, apply_fn, root):
        try:
            root.configure(cursor="")
        except Exception:
            pass
        if not ok:
            messagebox.showerror("AI suggestions", str(result), parent=self.host)
            return
        if not result:
            messagebox.showinfo(
                "AI suggestions",
                "The model had no replacements (text may be intentional).",
                parent=self.host,
            )
            return
        menu = tk.Menu(self.host, tearoff=0)
        menu.add_command(label="AI suggestions", state="disabled")
        menu.add_separator()
        for suggestion in result:
            menu.add_command(
                label=suggestion,
                command=lambda s=suggestion: apply_fn(s),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


class SpellCheckTextController(_SpellAiMixin):
    """Debounced offline spell + grammar lint with underlines and right-click fixes."""

    def __init__(
        self,
        host,
        text_widget,
        get_engine,
        service=None,
        is_enabled=None,
        is_grammar_enabled=None,
        is_synonyms_enabled=None,
        debounce_ms=900,
    ):
        self.host = host
        self.text = text_widget
        self.get_engine = get_engine
        self.service = service or SpellCheckService()
        self.is_enabled = is_enabled or (lambda: True)
        self.is_grammar_enabled = is_grammar_enabled or (lambda: True)
        self.is_synonyms_enabled = is_synonyms_enabled or synonyms_enabled
        self.debounce_ms = debounce_ms
        self._after_id = None
        self._menu = None
        self._attached = False
        self._active_issue = None
        self._grammar_issues = []

    def attach(self):
        if self._attached:
            return
        self._attached = True
        self.text.tag_configure(
            SPELL_ERROR_TAG,
            underline=True,
            foreground="#E57373",
        )
        self.text.tag_configure(
            GRAMMAR_ERROR_TAG,
            underline=True,
            foreground="#FFB74D",
        )
        self.text.bind("<KeyRelease>", self._on_edit, add="+")
        for seq in ("<<Paste>>", "<<Cut>>"):
            try:
                self.text.bind(seq, self._on_edit, add="+")
            except tk.TclError:
                pass
        self.text.bind("<Button-3>", self._on_right_click, add="+")
        self.schedule_refresh()

    def detach(self):
        if not self._attached:
            return
        self._attached = False
        self._cancel_debounce()
        self.clear_marks()
        try:
            self.text.unbind("<KeyRelease>", self._on_edit)
            self.text.unbind("<Button-3>", self._on_right_click)
        except Exception:
            pass

    def _lint_active(self):
        """True when spell or grammar underlines should run."""
        return self.is_enabled() or self.is_grammar_enabled()

    def _interaction_active(self):
        """True when right-click menus should respond (includes synonyms-only)."""
        return self._lint_active() or self.is_synonyms_enabled()

    def _on_edit(self, event=None):
        self.schedule_refresh()

    def schedule_refresh(self):
        if not self._attached or not self._lint_active():
            self.clear_marks()
            return
        self._cancel_debounce()
        self._after_id = self.host.after(self.debounce_ms, self.refresh)

    def _cancel_debounce(self):
        if self._after_id is not None:
            try:
                self.host.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def clear_marks(self):
        try:
            self.text.tag_remove(SPELL_ERROR_TAG, "1.0", "end")
            self.text.tag_remove(GRAMMAR_ERROR_TAG, "1.0", "end")
        except tk.TclError:
            pass
        self._grammar_issues = []

    def refresh(self):
        self._after_id = None
        if not self._attached or not self._lint_active():
            self.clear_marks()
            return
        if str(self.text.cget("state")) == "disabled":
            self.clear_marks()
            return

        text = self.text.get("1.0", "end-1c")
        engine = self.get_engine()
        if engine is None:
            return

        spell_on = self.is_enabled()
        grammar_on = self.is_grammar_enabled()

        def worker():
            try:
                issues = self.service.scan_prose(engine, text, grammar=grammar_on)
                if not spell_on:
                    issues = [i for i in issues if i.get("kind") != "spelling"]
            except Exception:
                issues = []
            self.host.after(0, lambda: self._apply_issues(issues))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_issues(self, issues):
        if not self._attached or not self._lint_active():
            return
        self.clear_marks()
        self._grammar_issues = []
        for issue in issues:
            kind = issue.get("kind", "spelling")
            tag = GRAMMAR_ERROR_TAG if kind == "grammar" else SPELL_ERROR_TAG
            try:
                start = char_offset_to_index(self.text, issue["start"])
                end = char_offset_to_index(self.text, issue["end"])
                self.text.tag_add(tag, start, end)
                if kind == "grammar":
                    self._grammar_issues.append(issue)
            except tk.TclError:
                continue

    def _on_right_click(self, event):
        """Route click to grammar, spell, or synonyms menu by word under cursor."""
        if not self._interaction_active():
            return
        index = self.text.index(f"@{event.x},{event.y}")
        offset = index_to_char_offset(self.text, index)
        grammar_hit = grammar_issue_at_offset(self._grammar_issues, offset)
        if grammar_hit and self.is_grammar_enabled():
            self._active_issue = grammar_hit
            self._show_grammar_menu(event, grammar_hit)
            return

        hit = word_at_index(self.text, index)
        if not hit:
            return
        word, start, end = hit
        engine = self.get_engine()
        if engine is None:
            return

        spell_on = self.is_enabled()
        syn_on = self.is_synonyms_enabled()
        misspelled = False
        suggestions = []
        if spell_on:
            checker = self.service.get_checker(engine)
            misspelled = not checker.is_correct(word)
            if misspelled:
                suggestions = checker.suggestions(word)

        if misspelled:
            self._active_issue = {"word": word, "start": start, "end": end, "kind": "spelling"}
            self._show_spell_menu(event, word, suggestions)
            return

        if syn_on:
            self._active_issue = {"word": word, "start": start, "end": end, "kind": "spelling"}
            self._show_synonyms_menu(event, word)

    def _show_spell_menu(self, event, word, suggestions):
        if self._menu is not None:
            try:
                self._menu.destroy()
            except Exception:
                pass
        self._menu = tk.Menu(self.text, tearoff=0)
        if suggestions:
            for suggestion in suggestions[:8]:
                self._menu.add_command(
                    label=suggestion,
                    command=lambda s=suggestion: self._replace_spell_active(s),
                )
            self._menu.add_separator()
        _append_synonyms_cascade(self._menu, word, self._replace_spell_active)
        self._menu.add_command(
            label=_dictionary_add_label(word),
            command=lambda: self._add_to_dictionary(word),
        )
        _append_ai_suggest_item(
            self._menu,
            lambda: self._request_ai_suggestions(
                event,
                word,
                self._context_for_active_issue(),
                "",
                self._replace_spell_active,
            ),
        )
        self._menu.add_separator()
        self._menu.add_command(
            label=_ignore_label(word),
            command=lambda: self._ignore_word(word),
        )
        _popup_menu(self._menu, event)

    def _show_synonyms_menu(self, event, word):
        """Flat synonym list for correctly spelled words (synonyms-only mode)."""
        if self._menu is not None:
            try:
                self._menu.destroy()
            except Exception:
                pass
        self._menu = tk.Menu(self.text, tearoff=0)
        syns = fetch_synonyms(word)
        if syns:
            for syn in syns:
                self._menu.add_command(
                    label=syn,
                    command=lambda s=syn: self._replace_spell_active(s),
                )
        else:
            from synonyms import wordnet_available, wordnet_error

            if not wordnet_available():
                hint = wordnet_error() or "WordNet data not available."
                self._menu.add_command(label=f"Unavailable ({hint[:40]})", state="disabled")
            else:
                self._menu.add_command(label="No synonyms found", state="disabled")
        _popup_menu(self._menu, event)

    def _show_grammar_menu(self, event, issue):
        if self._menu is not None:
            try:
                self._menu.destroy()
            except Exception:
                pass
        self._menu = tk.Menu(self.text, tearoff=0)
        self._menu.add_command(label=issue.get("message", "Grammar issue"), state="disabled")
        replacement = issue.get("replacement")
        if replacement:
            self._menu.add_separator()
            self._menu.add_command(
                label=f"Fix: {replacement}",
                command=lambda: self._apply_grammar_fix(issue),
            )
        flagged = self.text.get("1.0", "end-1c")[
            issue["start"] : issue["end"]
        ]
        _append_ai_suggest_item(
            self._menu,
            lambda: self._request_ai_suggestions(
                event,
                flagged,
                self._context_for_grammar_issue(issue),
                issue.get("message", ""),
                lambda s: self._apply_grammar_fix(
                    {**issue, "replacement": s, "start": issue["start"], "end": issue["end"]}
                ),
            ),
        )
        self._menu.add_separator()
        self._menu.add_command(
            label=_ignore_grammar_label(),
            command=lambda: self._ignore_grammar(issue),
        )
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _replace_spell_active(self, replacement):
        issue = self._active_issue
        if not issue or issue.get("kind") != "spelling":
            return
        try:
            self.text.delete(issue["start"], issue["end"])
            self.text.insert(issue["start"], replacement)
        except tk.TclError:
            return
        self._active_issue = None
        self.schedule_refresh()

    def _apply_grammar_fix(self, issue):
        replacement = issue.get("replacement")
        if replacement is None:
            return
        try:
            start = char_offset_to_index(self.text, issue["start"])
            end = char_offset_to_index(self.text, issue["end"])
            self.text.delete(start, end)
            self.text.insert(start, replacement)
        except tk.TclError:
            return
        self._active_issue = None
        self.schedule_refresh()

    def _context_for_active_issue(self):
        full = self.text.get("1.0", "end-1c")
        issue = self._active_issue
        if not issue or issue.get("kind") != "spelling":
            return full[:500]
        start = index_to_char_offset(self.text, issue["start"])
        end = index_to_char_offset(self.text, issue["end"])
        return extract_local_context(full, start, end)

    def _context_for_grammar_issue(self, issue):
        full = self.text.get("1.0", "end-1c")
        return extract_local_context(full, issue["start"], issue["end"])

    def _add_to_dictionary(self, word):
        engine = self.get_engine()
        if engine is None:
            return
        self.service.add_word(engine, word)
        self._active_issue = None
        self.schedule_refresh()

    def _ignore_word(self, word):
        engine = self.get_engine()
        if engine is None:
            return
        self.service.ignore_word(engine, word)
        self._active_issue = None
        self.schedule_refresh()

    def _ignore_grammar(self, issue):
        engine = self.get_engine()
        if engine is None:
            return
        text = self.text.get("1.0", "end-1c")
        self.service.ignore_grammar(engine, issue, text)
        self._active_issue = None
        self.schedule_refresh()


class SpellCheckEntryController(_SpellAiMixin):
    """Lightweight spell + grammar lint for single-line CTkEntry choice fields."""

    def __init__(
        self,
        host,
        entry_widget,
        get_engine,
        service=None,
        is_enabled=None,
        is_grammar_enabled=None,
        is_synonyms_enabled=None,
        debounce_ms=900,
    ):
        self.host = host
        self.entry = entry_widget
        self._tk_entry = entry_widget
        if hasattr(entry_widget, "_entry"):
            self._tk_entry = entry_widget._entry
        self.get_engine = get_engine
        self.service = service or SpellCheckService()
        self.is_enabled = is_enabled or (lambda: True)
        self.is_grammar_enabled = is_grammar_enabled or (lambda: True)
        self.is_synonyms_enabled = is_synonyms_enabled or synonyms_enabled
        self.debounce_ms = debounce_ms
        self._after_id = None
        self._attached = False
        self._default_border = None
        self._issues = []
        self._menu = None

    def attach(self):
        if self._attached:
            return
        self._attached = True
        try:
            self._default_border = self.entry.cget("border_color")
        except Exception:
            self._default_border = None
        self._tk_entry.bind("<KeyRelease>", self._on_edit, add="+")
        self._tk_entry.bind("<FocusOut>", self._on_edit, add="+")
        self._tk_entry.bind("<Button-3>", self._on_right_click, add="+")
        self.schedule_refresh()

    def detach(self):
        if not self._attached:
            return
        self._attached = False
        self._cancel_debounce()
        self._set_ok_border()
        try:
            self._tk_entry.unbind("<KeyRelease>", self._on_edit)
            self._tk_entry.unbind("<FocusOut>", self._on_edit)
            self._tk_entry.unbind("<Button-3>", self._on_right_click)
        except Exception:
            pass

    def _lint_active(self):
        """True when spell or grammar underlines should run."""
        return self.is_enabled() or self.is_grammar_enabled()

    def _interaction_active(self):
        """True when right-click menus should respond (includes synonyms-only)."""
        return self._lint_active() or self.is_synonyms_enabled()

    def _on_edit(self, event=None):
        self.schedule_refresh()

    def schedule_refresh(self):
        if not self._attached or not self._lint_active():
            self._set_ok_border()
            return
        self._cancel_debounce()
        self._after_id = self.host.after(self.debounce_ms, self.refresh)

    def _cancel_debounce(self):
        if self._after_id is not None:
            try:
                self.host.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _set_ok_border(self):
        try:
            self.entry.configure(border_color=self._default_border or ("#565B5E", "#565B5E"))
        except Exception:
            pass

    def _set_error_border(self, grammar_only=False):
        color = "#FFB74D" if grammar_only else "#E57373"
        try:
            self.entry.configure(border_color=color)
        except Exception:
            pass

    def refresh(self):
        self._after_id = None
        if not self._attached or not self._lint_active():
            self._set_ok_border()
            return
        text = self.entry.get().strip()
        if not text:
            self._set_ok_border()
            return
        engine = self.get_engine()
        if engine is None:
            return

        spell_on = self.is_enabled()
        grammar_on = self.is_grammar_enabled()

        def worker():
            try:
                issues = self.service.scan_prose(engine, text, grammar=grammar_on)
                if not spell_on:
                    issues = [i for i in issues if i.get("kind") != "spelling"]
            except Exception:
                issues = []
            self.host.after(0, lambda: self._apply_issues(issues))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_issues(self, issues):
        if not self._attached or not self._lint_active():
            return
        self._issues = issues
        if not issues:
            self._set_ok_border()
            return
        has_spelling = any(i.get("kind") != "grammar" for i in issues)
        self._set_error_border(grammar_only=not has_spelling)

    def _on_right_click(self, event):
        """Issue menus first; fall back to word-at-cursor synonyms on clean entries."""
        if not self._interaction_active():
            return

        grammar_hits = [i for i in self._issues if i.get("kind") == "grammar"]
        spell_hits = [i for i in self._issues if i.get("kind") != "grammar"]
        if grammar_hits and self.is_grammar_enabled():
            self._active_issue = grammar_hits[0]
            self._show_grammar_menu(event, grammar_hits[0])
            return
        if spell_hits and self.is_enabled():
            issue = spell_hits[0]
            self._active_issue = issue
            self._show_spell_menu(event, issue.get("word", ""), issue.get("suggestions", []))
            return

        if not self.is_synonyms_enabled():
            return
        hit = word_at_entry_index(self._tk_entry, event)
        if not hit:
            return
        word, start, end = hit
        self._active_issue = {"word": word, "start": start, "end": end, "kind": "spelling"}
        self._show_synonyms_menu(event, word)

    def _show_spell_menu(self, event, word, suggestions):
        if self._menu is not None:
            try:
                self._menu.destroy()
            except Exception:
                pass
        self._menu = tk.Menu(self._tk_entry, tearoff=0)
        if suggestions:
            for suggestion in suggestions[:8]:
                self._menu.add_command(
                    label=suggestion,
                    command=lambda s=suggestion: self._replace_text(s),
                )
            self._menu.add_separator()
        _append_synonyms_cascade(self._menu, word, self._replace_word_in_entry)
        self._menu.add_command(
            label=_dictionary_add_label(word),
            command=lambda: self._add_to_dictionary(word),
        )
        _append_ai_suggest_item(
            self._menu,
            lambda: self._request_ai_suggestions(
                event,
                word,
                self.entry.get().strip(),
                "",
                self._replace_word_in_entry,
            ),
        )
        self._menu.add_separator()
        self._menu.add_command(
            label=_ignore_label(word),
            command=lambda: self._ignore_word(word),
        )
        _popup_menu(self._menu, event)

    def _show_synonyms_menu(self, event, word):
        """Flat synonym list for correctly spelled words (synonyms-only mode)."""
        if self._menu is not None:
            try:
                self._menu.destroy()
            except Exception:
                pass
        self._menu = tk.Menu(self._tk_entry, tearoff=0)
        syns = fetch_synonyms(word)
        if syns:
            for syn in syns:
                self._menu.add_command(
                    label=syn,
                    command=lambda s=syn: self._replace_word_in_entry(s),
                )
        else:
            from synonyms import wordnet_available, wordnet_error

            if not wordnet_available():
                hint = wordnet_error() or "WordNet data not available."
                self._menu.add_command(label=f"Unavailable ({hint[:40]})", state="disabled")
            else:
                self._menu.add_command(label="No synonyms found", state="disabled")
        _popup_menu(self._menu, event)

    def _show_grammar_menu(self, event, issue):
        if self._menu is not None:
            try:
                self._menu.destroy()
            except Exception:
                pass
        self._menu = tk.Menu(self._tk_entry, tearoff=0)
        self._menu.add_command(label=issue.get("message", "Grammar issue"), state="disabled")
        replacement = issue.get("replacement")
        if replacement:
            self._menu.add_separator()
            self._menu.add_command(
                label=f"Fix: {replacement}",
                command=lambda: self._replace_text(replacement),
            )
        flagged = self.entry.get()[issue["start"] : issue["end"]]
        _append_ai_suggest_item(
            self._menu,
            lambda: self._request_ai_suggestions(
                event,
                flagged,
                self.entry.get().strip(),
                issue.get("message", ""),
                lambda s: self._replace_span_in_entry(issue, s),
            ),
        )
        self._menu.add_separator()
        self._menu.add_command(
            label=_ignore_grammar_label(),
            command=lambda: self._ignore_grammar(issue),
        )
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _replace_text(self, replacement):
        self.entry.delete(0, "end")
        self.entry.insert(0, replacement)
        self.schedule_refresh()

    def _replace_word_in_entry(self, replacement):
        issue = self._active_issue
        text = self.entry.get()
        if issue and issue.get("word"):
            word = issue["word"]
            start = text.lower().find(word.lower())
            if start >= 0:
                end = start + len(word)
                new_text = text[:start] + replacement + text[end:]
                self.entry.delete(0, "end")
                self.entry.insert(0, new_text)
                self.schedule_refresh()
                return
        self._replace_text(replacement)

    def _replace_span_in_entry(self, issue, replacement):
        text = self.entry.get()
        start = issue.get("start", 0)
        end = issue.get("end", len(text))
        new_text = text[:start] + replacement + text[end:]
        self.entry.delete(0, "end")
        self.entry.insert(0, new_text)
        self.schedule_refresh()

    def _add_to_dictionary(self, word):
        engine = self.get_engine()
        if engine is None:
            return
        self.service.add_word(engine, word)
        self.schedule_refresh()

    def _ignore_word(self, word):
        engine = self.get_engine()
        if engine is None:
            return
        self.service.ignore_word(engine, word)
        self.schedule_refresh()

    def _ignore_grammar(self, issue):
        engine = self.get_engine()
        if engine is None:
            return
        self.service.ignore_grammar(engine, issue, self.entry.get())
        self.schedule_refresh()
