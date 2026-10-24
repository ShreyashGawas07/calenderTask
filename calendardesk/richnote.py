"""Notes with bullets, numbered lists and bold, stored as a tiny markdown subset:
lines starting "- " (bullet) or "1. " (numbered), and **bold** spans. Everything else is plain text."""
import re
import tkinter as tk
import tkinter.font as tkfont

NUMBER = re.compile(r"(\d+)\. ")
BULLET_SHOWN = "• "
CHANGE_DELAY_MS = 600


def _split_bold(text):
    """'a **b** c' -> ('a b c', [(2, 3)]). An unclosed ** stays as literal text."""
    plain, spans, pos = [], [], 0
    for m in re.finditer(r"\*\*(.+?)\*\*", text):
        plain.append(text[pos:m.start()])
        start = sum(map(len, plain))
        plain.append(m.group(1))
        spans.append((start, start + len(m.group(1))))
        pos = m.end()
    plain.append(text[pos:])
    return "".join(plain), spans


def list_number(line, prev):
    """The list number that starts `line`, or None. A list starts at 1 and goes on from the line
    above (`prev`: its number, or None), so "2024. was a good year" is plain text, not item 2024."""
    m = NUMBER.match(line)
    if not m:
        return None
    n = int(m.group(1))
    # n == prev: a line Enter just inserted into a list, renumbered right after
    return n if n == 1 or (prev is not None and n in (prev, prev + 1)) else None


def parse_lines(md):
    """Markdown subset -> [(kind, text, bold_spans)] with kind 'bullet', 'number' or 'plain'."""
    lines, prev = [], None
    for line in md.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        kind, num = "plain", None
        if line.startswith(("- ", BULLET_SHOWN)):
            kind, line = "bullet", line[2:]
        elif (num := list_number(line, prev)) is not None:
            kind, line = "number", line[NUMBER.match(line).end():]
        prev = num
        text, spans = _split_bold(line)
        lines.append((kind, text, spans))
    return lines


def _join_bold(text, spans):
    out, pos = [], 0
    for a, b in sorted(spans):
        if b <= a or a < pos:
            continue
        out += [text[pos:a], "**", text[a:b], "**"]
        pos = b
    out.append(text[pos:])
    return "".join(out)


def to_markdown(lines):
    """Inverse of parse_lines. Consecutive numbered lines are numbered 1, 2, 3…"""
    out, n = [], 0
    for kind, text, spans in lines:
        n = n + 1 if kind == "number" else 0
        prefix = {"bullet": "- ", "number": f"{n}. "}.get(kind, "")
        out.append(prefix + _join_bold(text, spans))
    return "\n".join(out)


class RichNote(tk.Text):
    """A Text widget that shows bullets as '• ', numbers as '1. ' and bold as a bold font.
    Fires <<NoteChanged>> once typing has stopped for a moment."""

    def __init__(self, master, **kw):
        kw.setdefault("wrap", "word")
        kw.setdefault("undo", True)
        super().__init__(master, **kw)
        self._job = None
        self._loading = False
        self.restyle()
        self.bind("<Return>", lambda e: self.newline() or "break")
        self.bind("<<Modified>>", self._modified)
        self.bind("<KeyRelease>", lambda e: self._style_line(int(self.index("insert").split(".")[0])), add="+")
        self.bind("<Control-b>", lambda e: self.toggle_bold() or "break")

    def restyle(self):
        """Re-read the widget font (after a theme or size change) for the bold and list tags."""
        base = tkfont.Font(font=self.cget("font"))
        bold = base.actual()
        bold["weight"] = "bold"
        self._bold_font = tkfont.Font(**bold)
        indent = base.measure("00. ")
        self.tag_configure("bold", font=self._bold_font)
        self.tag_configure("list", lmargin1=0, lmargin2=indent)

    # -- load / save -------------------------------------------------------------
    def load(self, md):
        self._loading = True
        self.delete("1.0", "end")
        number = 0
        for i, (kind, text, spans) in enumerate(parse_lines(md or "")):
            number = number + 1 if kind == "number" else 0
            prefix = {"bullet": BULLET_SHOWN, "number": f"{number}. "}.get(kind, "")
            row = i + 1
            self.insert(f"{row}.0" if i == 0 else "end", ("\n" if i else "") + prefix + text)
            for a, b in spans:
                self.tag_add("bold", f"{row}.{len(prefix) + a}", f"{row}.{len(prefix) + b}")
            self._style_line(row)
        self.edit_reset()
        self.edit_modified(False)
        self._loading = False

    def dump(self):
        lines = []
        kinds = self._kinds()
        for row in range(1, self._rows() + 1):
            line = self.get(f"{row}.0", f"{row}.end")
            kind, start = kinds[row - 1]
            spans = []
            for a, b in self._bold_ranges(row):
                a, b = max(a, start), b
                if b > a:
                    spans.append((a - start, b - start))
            lines.append((kind, line[start:], spans))
        return to_markdown(lines)

    # -- formatting commands ------------------------------------------------------
    def toggle_bullet(self):
        rows = self._selected_rows()
        kinds = self._kinds()  # read before changing: a line's kind depends on the line above
        on = all(kinds[r - 1][0] == "bullet" for r in rows)
        for r in rows:
            self._set_prefix(r, "" if on else BULLET_SHOWN, kinds[r - 1][1])
        self._renumber()
        self._changed_now()

    def toggle_number(self):
        rows = self._selected_rows()
        kinds = self._kinds()  # read before changing: a line's kind depends on the line above
        on = all(kinds[r - 1][0] == "number" for r in rows)
        for r in rows:
            self._set_prefix(r, "" if on else "1. ", kinds[r - 1][1])
        self._renumber()
        self._changed_now()

    def toggle_bold(self):
        try:
            a, b = self.index("sel.first"), self.index("sel.last")
        except tk.TclError:
            return
        whole = all("bold" in self.tag_names(f"{a}+{i}c") for i in range(len(self.get(a, b))) if self.get(f"{a}+{i}c") != "\n")
        (self.tag_remove if whole else self.tag_add)("bold", a, b)
        self._changed_now()

    def newline(self):
        """Enter: continue a list (and renumber), or end it when the current item is empty."""
        row = int(self.index("insert").split(".")[0])
        line = self._line(row)
        kind, start = self._kind(row)
        if kind == "plain":
            self.insert("insert", "\n")
        elif not line[start:].strip():
            self._set_prefix(row, "")
        else:
            self.insert("insert", "\n" + (BULLET_SHOWN if kind == "bullet" else "1. "))
            self._style_line(row + 1)
            self._renumber()
        self.see("insert")

    # -- helpers ------------------------------------------------------------------
    def _rows(self):
        return int(self.index("end-1c").split(".")[0])

    def _line(self, row):
        return self.get(f"{row}.0", f"{row}.end")

    def _kinds(self, last=None):
        """(kind, prefix length) of each line up to row `last` (default: all)."""
        out, prev = [], None
        for row in range(1, (last or self._rows()) + 1):
            line = self._line(row)
            num = None
            if line.startswith(BULLET_SHOWN) or line.startswith("- "):
                out.append(("bullet", 2))
            elif (num := list_number(line, prev)) is not None:
                out.append(("number", NUMBER.match(line).end()))
            else:
                out.append(("plain", 0))
            prev = num
        return out

    def _kind(self, row):
        return self._kinds(row)[-1]

    def _bold_ranges(self, row):
        """Bold column ranges on one line."""
        out, pos = [], f"{row}.0"
        end = self.index(f"{row}.end")
        while (r := self.tag_nextrange("bold", pos, end)):
            stop = r[1] if self.compare(r[1], "<=", end) else end
            out.append((int(r[0].split(".")[1]), int(stop.split(".")[1])))
            pos = r[1]
        return out

    def _selected_rows(self):
        try:
            a = int(self.index("sel.first").split(".")[0])
            last = self.index("sel.last")
            b = int(last.split(".")[0])
            if last.endswith(".0") and b > a:
                b -= 1  # a selection ending at the start of a line doesn't include that line
        except tk.TclError:
            a = b = int(self.index("insert").split(".")[0])
        return range(a, min(b, self._rows()) + 1)

    def _set_prefix(self, row, prefix, start=None):
        if start is None:
            _, start = self._kind(row)
        self.delete(f"{row}.0", f"{row}.{start}")
        if prefix:
            self.insert(f"{row}.0", prefix)
            self.tag_remove("bold", f"{row}.0", f"{row}.{len(prefix)}")
        self._style_line(row)

    def _renumber(self):
        n, prev = 0, None
        for row in range(1, self._rows() + 1):
            line = self._line(row)
            prev = list_number(line, prev)
            if prev is None:
                n = 0
                continue
            n += 1
            m = NUMBER.match(line)
            if m.group(1) != str(n):
                self.delete(f"{row}.0", f"{row}.{len(m.group(1))}")
                self.insert(f"{row}.0", str(n))

    def _style_line(self, row):
        kind, _ = self._kind(row)
        if kind == "plain":
            self.tag_remove("list", f"{row}.0", f"{row}.end+1c")
        else:
            self.tag_add("list", f"{row}.0", f"{row}.end+1c")

    def _modified(self, _event=None):
        if not self.edit_modified():
            return
        self.edit_modified(False)
        if self._loading:
            return
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(CHANGE_DELAY_MS, self._fire)

    def _changed_now(self):
        """Formatting changes (tags) don't set Tk's modified flag, so schedule the save directly."""
        self.edit_modified(True)
        self._modified()

    def _fire(self):
        self._job = None
        self.event_generate("<<NoteChanged>>")

    def destroy(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        super().destroy()
