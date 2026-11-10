import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import history
import scan


class HistoryTests(unittest.TestCase):
    def test_session_binding_is_unique_and_does_not_guess_by_folder(self):
        a = "The first agent generated a distinctive image and explained its green floating fragment. " * 3
        b = "The other agent implemented a local files gallery with a different set of outputs. " * 3
        candidates = [("mascot", [a]), ("gallery", [b])]
        self.assertEqual(history.bind_text(candidates, a, ""), "mascot")
        self.assertEqual(history.bind_text(candidates, b, ""), "gallery")
        self.assertIsNone(history.bind_text(candidates, "unrelated" * 20, ""))
        self.assertIsNone(history.bind_text([("one", [a]), ("two", [a])], a, ""))
        self.assertIsNone(history.bind_text(candidates, a + "A new conversation is streaming content that has not reached its persisted message yet." * 2, ""))

    def test_last_50_counts_messages_and_includes_generation_inside_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = sqlite3.connect(root / "thread_history_1.sqlite")
            db.execute("CREATE TABLE thread_items(thread_id, rollout_ordinal, created_at_ms, item_type, item_json)")
            for i in range(1, 61):
                item = {"type": "agentMessage", "text": f"/output/file-{i}.md"}
                db.execute("INSERT INTO thread_items VALUES(?,?,?,?,?)", ("session", i * 10, i, item["type"], json.dumps(item)))
            for ordinal in (105, 595):
                item = {"type": "imageGeneration", "savedPath": f"/output/image-{ordinal}.png", "result": "base64" * 100}
                db.execute("INSERT INTO thread_items VALUES(?,?,?,?,?)", ("session", ordinal, 1, item["type"], json.dumps(item)))
            db.commit()
            db.close()
            messages, count = history.projected_messages(root, "session", "/output")
            self.assertEqual(count, 50)
            text = "\n".join(x["text"] for x in messages)
            self.assertIn("file-11.md", text)
            self.assertNotIn("file-10.md", text)
            self.assertNotIn("image-105.png", text)
            self.assertIn("image-595.png", text)
            self.assertEqual(messages[0]["text"], "/output/file-60.md")

    def test_latest_mention_wins_even_when_old_file_has_newer_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            new, old = root / "new.md", root / "old.md"
            new.write_text("new")
            old.write_text("old")
            os.utime(new, (1, 1))
            os.utime(old, (999999999, 999999999))
            messages = [dict(text=f"`{new}`", cwd=tmp, ordinal=30),
                        dict(text=f"`{old}`\n`{new}`", cwd=tmp, ordinal=20)]
            with patch.object(scan, "read_history", return_value=dict(messages=messages, message_count=2, session="selected")):
                result = scan.scan(dict(terminal="agent", app_home=tmp))
            self.assertEqual([x["name"] for x in result["items"]], ["new.md", "old.md"])
            self.assertEqual(result["items"][0]["ordinal"], 30)

    def test_does_not_add_global_generated_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = root / ".codex/generated_images/another-session.png"
            other.parent.mkdir(parents=True)
            other.write_text("unrelated")
            own = root / "own.md"
            own.write_text("selected session")
            messages = [dict(text=f"`{own}`", cwd=tmp)]
            with patch.object(scan, "read_history", return_value=dict(messages=messages, message_count=1)), patch.object(Path, "home", return_value=root):
                result = scan.scan(dict(terminal="agent", app_home=tmp, recent=True))
            self.assertEqual([x["name"] for x in result["items"]], ["own.md"])

    def test_generation_uses_saved_output_and_ignores_input_image(self):
        text = history.item_text(dict(type="imageGeneration", savedPath="/out/new.png", inputImages=["/in/old.png"], revisedPrompt="/prompt.md"))
        self.assertEqual(text, "/out/new.png")
        self.assertEqual(history.item_text(dict(type="commandExecution", command="cat /guide/SKILL.md", aggregatedOutput="/guide/secret.md")), "")
        self.assertEqual(history.item_text(dict(type="userMessage", content=[dict(type="text", text="/input.png")])), "")

    def test_paths_with_unicode_spaces_uri_and_line_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Türkçe resim (1).md"
            path.write_text("document")
            for text in (f"[dosya](<{path}>)", f"`{path}`", path.as_uri(), f"{path}:12:8"):
                self.assertIn(path, scan.references(text, tmp))
            self.assertIsNone(scan.resolve("file://another-host/tmp/file.md", tmp))

    def test_folder_outputs_and_hidden_search_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Brand assets"
            folder.mkdir()
            html = root / "report.html"
            html.write_text("<html>Report</html>")
            messages = [dict(text=f"Renkli maskotun yeni dosyaları:\n`{folder}`\n\nMaliyet karşılaştırması raporu:\n[raporu aç]({html})", cwd=tmp)]
            with patch.object(scan, "read_history", return_value=dict(messages=messages, message_count=1)):
                result = scan.scan(dict(terminal="agent", app_home=tmp))
            by_name = {x["name"]: x for x in result["items"]}
            self.assertEqual(by_name["Brand assets"]["kind"], "folder")
            self.assertEqual(by_name["report.html"]["kind"], "html")
            self.assertIn("Maliyet karşılaştırması", by_name["report.html"]["search_text"])
            self.assertIn("Renkli maskotun", by_name["Brand assets"]["search_text"])

    def test_search_context_merges_older_mentions_without_changing_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "result.html"
            p.write_text("result")
            messages = [dict(text=f"Son sürüm: `{p}`", cwd=tmp, ordinal=10),
                        dict(text=f"Önceki bütçe analizi: `{p}`", cwd=tmp, ordinal=5)]
            with patch.object(scan, "read_history", return_value=dict(messages=messages, message_count=2)):
                result = scan.scan(dict(terminal="agent", app_home=tmp))
            self.assertEqual(len(result["items"]), 1)
            self.assertEqual(result["items"][0]["ordinal"], 10)
            self.assertIn("bütçe analizi", result["items"][0]["search_text"])

    def test_jsonl_read_is_newest_first_and_skips_partial_last_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            records = [{"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": str(i)}]}} for i in range(60)]
            path.write_text("\n".join(json.dumps(x) for x in records) + '\n{"partial":')
            messages, count = history.log_messages(path, "codex", tmp)
            self.assertEqual(count, 50)
            self.assertEqual(messages[0]["text"], "output_text\n59")
            self.assertEqual(messages[-1]["text"], "output_text\n10")


if __name__ == "__main__":
    unittest.main()
