import tkinter as tk
import unittest

from calendardesk.richnote import RichNote, parse_lines, to_markdown


def round_trip(md):
    return to_markdown(parse_lines(md))


class MarkdownTests(unittest.TestCase):
    def test_round_trip(self):
        md = "1. a\n2. **b** c\n- d\nplain"
        self.assertEqual(round_trip(md), md)

    def test_parse_kinds_and_bold(self):
        self.assertEqual(parse_lines("1. a\n2. **b** c\n• d\nplain"), [
            ("number", "a", []), ("number", "b c", [(0, 1)]), ("bullet", "d", []), ("plain", "plain", [])])

    def test_odd_lines_lose_nothing(self):
        self.assertEqual(round_trip("1.\n-\n**open\r\nline"), "1.\n-\n**open\nline")

    def test_bullet_dot_is_stored_as_dash(self):
        self.assertEqual(round_trip("• a"), "- a")

    def test_empty(self):
        self.assertEqual(round_trip(""), "")


class RichNoteWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.note = RichNote(self.root)

    def tearDown(self):
        self.note.destroy()

    def test_load_dump(self):
        md = "1. a\n2. **b** c\n- d\nplain **x**"
        self.note.load(md)
        self.assertEqual(self.note.dump(), md)
        self.assertEqual(self.note.get("3.0", "3.end"), "• d")

    def test_toggle_number_on_lines(self):
        self.note.load("x\ny\nz")
        self.note.tag_add("sel", "1.0", "end")
        self.note.toggle_number()
        self.assertEqual(self.note.dump(), "1. x\n2. y\n3. z")
        self.note.toggle_number()
        self.assertEqual(self.note.dump(), "x\ny\nz")

    def test_toggle_bullet_current_line(self):
        self.note.load("x\ny")
        self.note.mark_set("insert", "2.0")
        self.note.toggle_bullet()
        self.assertEqual(self.note.dump(), "x\n- y")

    def test_toggle_bold(self):
        self.note.load("hello world")
        self.note.tag_add("sel", "1.0", "1.5")
        self.note.toggle_bold()
        self.assertEqual(self.note.dump(), "**hello** world")
        self.note.toggle_bold()
        self.assertEqual(self.note.dump(), "hello world")

    def test_enter_continues_and_renumbers(self):
        self.note.load("1. a\n2. b")
        self.note.mark_set("insert", "1.end")
        self.note.newline()
        self.note.insert("insert", "new")
        self.assertEqual(self.note.dump(), "1. a\n2. new\n3. b")

    def test_enter_on_empty_item_ends_list(self):
        self.note.load("- a")
        self.note.mark_set("insert", "1.end")
        self.note.newline()
        self.note.newline()
        self.assertEqual(self.note.dump(), "- a\n")

    def test_changed_event_after_typing_stops(self):
        fired = []
        self.note.bind("<<NoteChanged>>", lambda e: fired.append(1))
        self.note.load("a")
        self.root.update()
        self.note.insert("end", "b")
        self.root.update()
        self.assertEqual(fired, [])
        self.root.after(700, self.root.quit)
        self.root.mainloop()
        self.assertEqual(fired, [1])
