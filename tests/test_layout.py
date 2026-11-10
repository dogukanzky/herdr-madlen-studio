"""Single terminals must keep the header that contains the Chat toggle."""
import json
from pathlib import Path
import unittest

class LayoutTests(unittest.TestCase):
    def test_borderless_terminal_keeps_always_visible_header(self):
        root=json.loads((Path(__file__).resolve().parents[1]/'theme/layouts/madlen-studio.json').read_text())
        def walk(n):
            yield n
            for c in n.get('children',[]):yield from walk(c)
        pane=next(n for n in walk(root) if n.get('id')=='main')['content']['pane']
        self.assertTrue(pane['lone'])
        self.assertEqual(pane['header']['reveal'],'always')
        self.assertEqual(pane['header']['content']['mod'],'madlen-pane')
        self.assertEqual(pane['border']['width'],0)
        self.assertEqual(pane['focus']['width'],0)
