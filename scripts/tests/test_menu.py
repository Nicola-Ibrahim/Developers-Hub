"""Exercise shared Bash menu recovery without invoking application tools."""

import os
import pty
import re
import select
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

MENU = Path(__file__).resolve().parents[1] / "shell/menu.sh"


class MenuTests(unittest.TestCase):
    def run_menu(self, script, data):
        return subprocess.run(
            [
                "bash",
                "-c",
                'set -euo pipefail; source "$1"; ' + script,
                "menu-test",
                str(MENU),
            ],
            check=False,
            input=data,
            text=True,
            capture_output=True,
            timeout=5,
        )

    def run_tty_menu(self, script, data, env=None):
        master, slave = pty.openpty()
        process = subprocess.Popen(
            [
                "bash",
                "-c",
                'set -euo pipefail; source "$1"; ' + script,
                "menu-test",
                str(MENU),
            ],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=env,
            close_fds=True,
        )
        os.close(slave)
        output = bytearray()
        try:
            time.sleep(0.05)
            os.write(master, data.encode())
            deadline = time.monotonic() + 5
            while process.poll() is None and time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        output.extend(os.read(master, 4096))
                    except OSError:
                        break
            if process.poll() is None:
                process.kill()
                self.fail("TTY menu did not exit after receiving the selection")
        finally:
            os.close(master)
        return process.returncode, output.decode(errors="replace")

    def test_bad_input_is_literal_and_reprompts(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "not-executed"
            result = self.run_menu(
                'menu_choose "Pick action" "Status" "Start"; printf "%s" "$MENU_CHOICE"',
                f"$(touch {marker})\n99\n2\n",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "2")
            self.assertFalse(marker.exists())

    def test_back_and_eof_do_not_execute_an_action(self):
        for data, expected in (
            ("b\n", "back"),
            ("0\n", "back"),
            ("", "quit"),
            ("q\n", "quit"),
        ):
            result = self.run_menu(
                'menu_choose "Pick" "Start"; printf "%s" "$MENU_CHOICE"', data
            )
            self.assertEqual(result.stdout, expected)
            self.assertEqual(result.returncode, 0)

    def test_empty_enter_quits_and_invalid_choice_reprompts(self):
        result = self.run_menu(
            'menu_choose "Pick action" "Status|Show current status" "Start"; printf "%s:%s" "$MENU_CHOICE" "${MENU_QUIT:-0}"',
            "bad\n\n",
        )
        self.assertEqual(result.stdout, "quit:1")
        self.assertIn("Invalid choice", result.stderr)

    def test_confirmation_quit_propagates_through_menu_run(self):
        result = self.run_menu(
            'action() { menu_confirm "Apply?" || return 0; }; menu_run action; printf "%s" "${MENU_QUIT:-0}"',
            "q\n",
        )
        self.assertEqual(result.stdout, "1")
        self.assertNotIn("Action finished", result.stderr)

    def test_failed_action_confirmation_reports_cancellation(self):
        result = self.run_menu(
            'action() { menu_confirm "Apply?"; }; menu_run action', "n\n"
        )
        self.assertIn("Action cancelled", result.stderr)
        self.assertNotIn("Action failed", result.stderr)

    def test_colors_only_on_tty_and_no_color_disables_them(self):
        env = os.environ.copy()
        env.pop("NO_COLOR", None)
        env["LANG"] = "C.UTF-8"
        env["TERM"] = "xterm-256color"
        code, output = self.run_tty_menu(
            'menu_choose "Choose" "Status|Show status"', "1\n", env
        )
        self.assertEqual(code, 0)
        self.assertIn("\x1b[1;36m", output)
        self.assertIn("╔", output)
        self.assertIn("║ DEVOPS HUB | Choose", output)
        self.assertIn("╚", output)
        env["NO_COLOR"] = ""
        code, output = self.run_tty_menu(
            'menu_choose "Choose" "Status|Show status"', "1\n", env
        )
        self.assertEqual(code, 0)
        self.assertNotIn("\x1b[", output)
        self.assertIn("╔", output)
        plain = self.run_menu('menu_choose "Choose" "Status|Show status"', "1\n")
        self.assertNotIn("\x1b[", plain.stderr)

    def test_closed_box_respects_terminal_width_including_indent(self):
        env = dict(os.environ, LANG="C.UTF-8", TERM="xterm-256color")
        env.pop("NO_COLOR", None)
        for width in (60, 80):
            code, output = self.run_tty_menu(
                f'COLUMNS={width}; menu_choose "Database management / Host" "Status"',
                "1\n",
                env,
            )
            self.assertEqual(code, 0)
            plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
            borders = [
                line
                for line in plain.splitlines()
                if line.startswith(("  ╔", "  ║", "  ╚"))
            ]
            self.assertEqual(len(borders), 3)
            self.assertTrue(all(len(line) == width for line in borders), borders)

    def test_action_failure_returns_to_prompt(self):
        result = self.run_menu(
            'menu_run bash -c "exit 17"; menu_choose "Try again" "Status"; printf "%s" "$MENU_CHOICE"',
            "1\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "1")
        self.assertIn("exit 17", result.stderr)

    def test_action_failure_restores_directory(self):
        result = self.run_menu(
            'before=$PWD; menu_run bash -c "cd /; exit 17"; [[ "$PWD" == "$before" ]] && printf restored',
            "",
        )
        self.assertEqual(result.stdout, "restored")

    def test_confirmation_recovers_but_defaults_to_no(self):
        script = 'if menu_confirm "Apply?"; then printf yes; else printf no; fi'
        self.assertEqual(self.run_menu(script, "wrong\ny\n").stdout, "yes")
        self.assertEqual(self.run_menu(script, "\n").stdout, "no")
        self.assertEqual(self.run_menu(script, "").stdout, "no")

    def test_required_text_can_be_corrected_or_cancelled(self):
        script = 'if menu_text "Message"; then printf "%s" "$MENU_TEXT"; else printf cancel; fi'
        self.assertEqual(
            self.run_menu(script, " \nadd project index\n").stdout, "add project index"
        )
        self.assertEqual(self.run_menu(script, "b\n").stdout, "cancel")


if __name__ == "__main__":
    unittest.main()
