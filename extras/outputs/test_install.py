from copy import deepcopy
import unittest

from install import add_launcher, has_launcher


class LayoutTests(unittest.TestCase):
    def test_preserves_custom_tabs_and_other_panels(self):
        tree = {"id": "root", "type": "row", "children": [
            {"id": "sidebar", "type": "block", "content": {"mod": "my-personal-sidebar"}},
            {"id": "work", "type": "column", "children": [
                {"id": "tabs", "type": "block", "size": {"px": 42}, "window_drag": True, "content": {"mod": "tabs-tasks", "props": {"custom": True}}},
                {"id": "main", "type": "block", "content": {"tab": "active"}},
            ]},
        ]}
        original = deepcopy(tree)
        actual = add_launcher(tree)
        self.assertTrue(has_launcher(actual))
        self.assertEqual(actual["children"][0], original["children"][0])
        self.assertEqual(actual["children"][1]["children"][1], original["children"][1]["children"][1])
        row = actual["children"][1]["children"][0]
        self.assertEqual(row["size"], {"px": 42})
        self.assertEqual(row["children"][0]["content"], original["children"][1]["children"][0]["content"])
        self.assertEqual(add_launcher(deepcopy(actual)), actual)

    def test_unusual_layout_keeps_tree_and_uses_movable_launcher(self):
        tree = {"id": "root", "type": "block", "content": {"terminal": "existing"}, "floating": [{"id": "old", "content": {"mod": "old-mod"}}]}
        actual = add_launcher(deepcopy(tree))
        self.assertEqual(actual["content"], tree["content"])
        self.assertEqual(actual["floating"][0], tree["floating"][0])
        self.assertEqual(actual["floating"][1]["content"]["mod"], "outputs-browser")


if __name__ == "__main__":
    unittest.main()
