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

    def test_number_that_is_not_a_list_is_kept(self):
        """BUG-4: only a list the user made (1, then the next number) is renumbered."""
        for md in ("2024. was a good year", "100. items", "3. third\n4. fourth", "1. a\n2. b\n2024. year"):
            self.assertEqual(round_trip(md), md)


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

    def test_number_that_is_not_a_list_survives_editing(self):
        """BUG-4: typing in a note keeps a line's own number."""
        for md, edited in (("2024. was a good year", "2024. was a good year X"), ("100. items", "100. items X"),
                           ("3. third\n4. fourth", "3. third X\n4. fourth")):
            self.note.load(md)
            self.assertEqual(self.note.get("1.0", "end-1c"), md)
            self.note.insert("1.end", " X")
            self.assertEqual(self.note.dump(), edited)

    def test_enter_and_toggle_leave_other_numbers_alone(self):
        self.note.load("1. a\n2024. year")
        self.note.mark_set("insert", "1.end")
        self.note.newline()
        self.note.insert("insert", "b")
        self.assertEqual(self.note.dump(), "1. a\n2. b\n2024. year")
        self.note.load("2024. year")
        self.note.mark_set("insert", "1.0")
        self.note.toggle_number()
        self.assertEqual(self.note.dump(), "1. 2024. year")

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
