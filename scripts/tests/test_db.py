"""Safe local database command and configuration tests; never contacts a database."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "helpers" / "local_database.py"
ENTRYPOINT = ROOT / "scripts" / "db.sh"


class LocalDatabaseHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "backend").mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_helper(
        self,
        target: str,
        content: str = "",
        env: dict[str, str] | None = None,
        native: bool = False,
    ):
        (self.root / "backend" / ".env").write_text(content, encoding="utf-8")
        command = ["python3", str(HELPER), "--target", target, "--root", str(self.root)]
        if native:
            command.append("--native")
        merged = {
            key: value
            for key, value in os.environ.items()
            if key in ("PATH", "SYSTEMROOT", "TMPDIR")
        }
        merged.update(env or {})
        return subprocess.run(
            command, text=True, capture_output=True, env=merged, check=False
        )

    def test_compose_accepts_local_service_without_disclosing_url(self) -> None:
        secret = "postgresql+psycopg://tester:do-not-print@postgres:5432/app"
        result = self.run_helper("compose", f"PLATFORM_DATABASE_URL={secret}\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_compose_rejects_interpolation_and_file_configuration(self) -> None:
        for value in (
            "PLATFORM_DATABASE_URL=${DATABASE_URL}\n",
            "PLATFORM_DATABASE_URL_FILE=/run/secrets/db\n",
        ):
            with self.subTest(value=value):
                result = self.run_helper("compose", value)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("DATABASE_URL", result.stderr)

    def test_compose_refuses_remote_or_query_redirect(self) -> None:
        for url in (
            "postgresql+psycopg://u:p@remote:5432/db",
            "postgresql+psycopg://u:p@postgres:5432/db?host=remote",
        ):
            result = self.run_helper("compose", f"PLATFORM_DATABASE_URL={url}\n")
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(url, result.stderr)

    def test_compose_refuses_libpq_redirect_and_server_environment(self) -> None:
        cases = (
            "PLATFORM_DATABASE_URL=postgresql+psycopg://u:p@postgres:5432/db\nPGSERVICE=remote\n",
            "PLATFORM_DATABASE_URL=postgresql+psycopg://u:p@postgres:5432/db\nPLATFORM_ENVIRONMENT=server\n",
        )
        for content in cases:
            result = self.run_helper("compose", content)
            self.assertNotEqual(result.returncode, 0)

    def test_ambiguous_url_value_and_file_are_refused(self) -> None:
        private = self.root / "url"
        private.write_text(
            "postgresql+psycopg://u:p@remote.example:5432/db\n", encoding="utf-8"
        )
        result = self.run_helper(
            "host",
            env={
                "PLATFORM_DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/db",
                "PLATFORM_DATABASE_URL_FILE": str(private),
            },
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("remote.example", result.stderr)

    def test_local_file_cannot_mask_a_remote_direct_setting(self) -> None:
        private = self.root / "url"
        private.write_text("postgresql+psycopg://u:p@localhost:5432/db")
        result = self.run_helper(
            "host",
            env={
                "PLATFORM_DATABASE_URL_FILE": str(private),
                "PLATFORM_DATABASE_URL": "postgresql+psycopg://u:p@remote.invalid/db",
            },
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("remote.invalid", result.stderr)

    def test_conflicting_case_configuration_is_refused(self) -> None:
        result = self.run_helper(
            "host",
            env={
                "PLATFORM_DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
                "platform_database_url": "postgresql+psycopg://u:p@remote.invalid/db",
            },
        )
        self.assertNotEqual(result.returncode, 0)

    def test_host_requires_loopback_and_rejects_libpq_redirection(self) -> None:
        local = "postgresql+psycopg://u:secret@localhost:5432/db"
        result = self.run_helper("host", env={"PLATFORM_DATABASE_URL": local})
        self.assertEqual(result.returncode, 0, result.stderr)
        redirected = self.run_helper(
            "host", env={"PLATFORM_DATABASE_URL": local, "PGHOSTADDR": "192.0.2.8"}
        )
        self.assertNotEqual(redirected.returncode, 0)
        self.assertNotIn("secret", redirected.stderr)
        remote = self.run_helper(
            "host",
            env={
                "PLATFORM_DATABASE_URL": "postgresql+psycopg://u:p@example.com:5432/db"
            },
        )
        self.assertNotEqual(remote.returncode, 0)
        nonstandard = self.run_helper(
            "host",
            env={"PLATFORM_DATABASE_URL": "postgresql+psycopg://u:p@localhost:5544/db"},
        )
        self.assertEqual(nonstandard.returncode, 0, nonstandard.stderr)

    def test_host_reads_private_url_file_without_echoing(self) -> None:
        private = self.root / "url"
        private.write_text(
            "postgresql+psycopg://u:private-value@[::1]:5432/db\n", encoding="utf-8"
        )
        result = self.run_helper(
            "host", env={"PLATFORM_DATABASE_URL_FILE": str(private)}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("private-value", result.stdout + result.stderr)

    def test_native_requires_local_runtime_pepper_and_loopback_opa(self) -> None:
        url = "postgresql+psycopg://u:p@localhost:5432/db"
        valid = {
            "PLATFORM_DATABASE_URL": url,
            "PLATFORM_TOKEN_PEPPER": "x" * 32,
            "PLATFORM_ENVIRONMENT": "local",
            "PLATFORM_OPA_URL": "http://127.0.0.1:8181",
        }
        self.assertEqual(self.run_helper("host", env=valid, native=True).returncode, 0)
        for changes in (
            {"PLATFORM_TOKEN_PEPPER": "short"},
            {"PLATFORM_ENVIRONMENT": "server"},
            {"PLATFORM_OPA_URL": "http://user:pass@opa:8181"},
        ):
            env = dict(valid)
            env.update(changes)
            result = self.run_helper("host", env=env, native=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("pass", result.stderr)


class DatabaseCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        (self.root / "backend").mkdir(parents=True)
        (self.root / "scripts/helpers").mkdir(parents=True)
        shutil.copytree(ROOT / "scripts/shell", self.root / "scripts/shell")
        shutil.copy(ENTRYPOINT, self.root / "scripts/db.sh")
        shutil.copy(HELPER, self.root / "scripts/helpers/local_database.py")
        self.entrypoint = self.root / "scripts/db.sh"
        (self.root / "backend/.env").write_text(
            "PLATFORM_ENVIRONMENT=local\nPLATFORM_DATABASE_URL=postgresql+psycopg://fake:synthetic@postgres:5432/local\n"
        )
        self.bin = Path(self.temp.name) / "bin"
        self.bin.mkdir()
        self.log = self.bin / "commands.log"
        docker = self.bin / "docker"
        docker.write_text(
            "#!/bin/sh\n"
            "printf 'docker' >> \"$DB_TEST_LOG\"\n"
            'for arg in "$@"; do printf \' <%s>\' "$arg" >> "$DB_TEST_LOG"; done\n'
            "printf '\\n' >> \"$DB_TEST_LOG\"\n"
            "exit 0\n",
            encoding="utf-8",
        )
        docker.chmod(0o755)
        uv = self.bin / "uv"
        uv.write_text(
            "#!/bin/sh\n"
            "printf 'uv' >> \"$DB_TEST_LOG\"\n"
            'for arg in "$@"; do printf \' <%s>\' "$arg" >> "$DB_TEST_LOG"; done\n'
            "printf '\\n' >> \"$DB_TEST_LOG\"\n"
            "exit 0\n",
            encoding="utf-8",
        )
        uv.chmod(0o755)
        self.env = {
            key: value
            for key, value in os.environ.items()
            if key in ("PATH", "SYSTEMROOT", "TMPDIR")
        }
        self.env.update(
            {
                "PATH": f"{self.bin}:{self.env['PATH']}",
                "DB_TEST_LOG": str(self.log),
                "DOCKER_HOST": "unix:///var/run/docker.sock",
                "PLATFORM_DATABASE_URL": "postgresql+psycopg://tester:secret@127.0.0.1:5432/local",
                "PLATFORM_ENVIRONMENT": "local",
                "PLATFORM_TOKEN_PEPPER": "p" * 32,
            }
        )
        for key in (
            "DATABASE_URL",
            "DATABASE_URL_FILE",
            "PLATFORM_DATABASE_URL_FILE",
            "PGSERVICE",
            "PGSERVICEFILE",
            "PGHOSTADDR",
        ):
            self.env.pop(key, None)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def invoke(
        self, *args: str, input_text: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.entrypoint), *args],
            text=True,
            input=input_text,
            capture_output=True,
            env=self.env,
            check=False,
        )

    def test_database_menu_reprompts_and_returns_between_levels(self) -> None:
        result = self.invoke("menu", input_text="2\n99\n2\nb\nq\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Invalid choice", result.stderr)
        self.assertIn("<history> <--verbose>", self.log.read_text())

    def test_database_menu_cancellation_and_eof_are_safe(self) -> None:
        result = self.invoke("menu", input_text="2\n7\nn\nb\nq\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.invoke("menu", input_text="").returncode, 0)

    def test_quit_from_revision_options_exits_without_commands(self) -> None:
        result = self.invoke("menu", input_text="2\n8\nadd index\nq\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())

    def test_quit_during_upgrade_confirmation_exits_menu(self) -> None:
        result = self.invoke("menu", input_text="2\n7\nq\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())

    def test_compose_uses_existing_migration_image_without_dependencies(self) -> None:
        self.assertEqual(self.invoke("compose", "history").returncode, 0)
        recorded = self.log.read_text(encoding="utf-8")
        self.assertIn("<--no-deps>", recorded)
        self.assertIn("<--pull>", recorded)
        self.assertIn("<never>", recorded)
        self.assertIn("<migrate>", recorded)
        self.assertLess(
            recorded.index("docker <info>"), recorded.index("docker <compose>")
        )
        self.assertNotIn("secret", recorded)

    def test_host_pins_offline_frozen_uv_invocation(self) -> None:
        self.assertEqual(self.invoke("host", "history").returncode, 0)
        recorded = self.log.read_text(encoding="utf-8")
        self.assertIn("<--offline>", recorded)
        self.assertIn("<--no-env-file>", recorded)
        self.assertIn("<--frozen>", recorded)
        self.assertIn("<--no-sync>", recorded)

    def test_read_commands_use_expected_alembic_arguments_on_both_targets(self) -> None:
        cases = (
            ("host", "status", ("<current>", "<heads>")),
            ("host", "current", ("<current>",)),
            ("compose", "current", ("<current>",)),
            ("compose", "heads", ("<heads>",)),
            ("compose", "status", ("<current>", "<heads>")),
            ("host", "history", ("<history>", "<--verbose>")),
            ("compose", "history", ("<history>", "<--verbose>")),
            ("host", "branches", ("<branches>", "<--verbose>")),
            ("compose", "branches", ("<branches>", "<--verbose>")),
            ("host", "check", ("<check>",)),
            ("compose", "check", ("<check>",)),
        )
        for target, action, expected in cases:
            with self.subTest(target=target, action=action):
                self.log.unlink(missing_ok=True)
                result = self.invoke(target, action)
                self.assertEqual(result.returncode, 0, result.stderr)
                recorded = self.log.read_text(encoding="utf-8")
                for item in expected:
                    self.assertIn(item, recorded)
                if action == "status":
                    self.assertLess(
                        recorded.index("<current>"), recorded.index("<heads>")
                    )
                self.assertNotIn("secret", recorded)

    def test_sql_preview_is_offline_sql_generation_and_never_upgrade_apply(
        self,
    ) -> None:
        for target in ("host", "compose"):
            with self.subTest(target=target):
                self.log.unlink(missing_ok=True)
                result = self.invoke(target, "sql")
                self.assertEqual(result.returncode, 0, result.stderr)
                recorded = self.log.read_text(encoding="utf-8")
                self.assertIn("<upgrade>", recorded)
                self.assertIn("<head>", recorded)
                self.assertIn("<--sql>", recorded)
                alembic_commands = [
                    line for line in recorded.splitlines() if "<upgrade> <head>" in line
                ]
                self.assertEqual(len(alembic_commands), 1)
                self.assertTrue(alembic_commands[0].endswith("<--sql>"))

    def test_upgrade_requires_yes_noninteractively(self) -> None:
        result = self.invoke("compose", "upgrade")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.invoke("compose", "upgrade", "--yes").returncode, 0)

    def test_help_and_no_argument_non_tty_are_side_effect_free(self) -> None:
        for arguments in ((), ("--help",), ("-h",), ("help",)):
            result = self.invoke(*arguments)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Usage:", result.stdout)
        self.assertFalse(self.log.exists())

    def test_revision_requires_yes_noninteractively(self) -> None:
        result = self.invoke("host", "revision", "--message", "safe migration")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())

    def test_unknown_options_are_rejected_before_docker(self) -> None:
        result = self.invoke("compose", "upgrade", "--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())

    def test_revision_requires_message_and_invokes_host_only(self) -> None:
        missing = self.invoke("host", "autogenerate-revision")
        self.assertNotEqual(missing.returncode, 0)
        self.assertFalse(self.log.exists())
        for action, autogenerate in (
            ("blank-revision", False),
            ("autogenerate-revision", True),
        ):
            with self.subTest(action=action):
                self.log.unlink(missing_ok=True)
                result = self.invoke(
                    "host", action, "--message", "safe migration", "--yes"
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                recorded = self.log.read_text(encoding="utf-8")
                self.assertIn("<revision>", recorded)
                self.assertIn("<--message> <safe migration>", recorded)
                self.assertEqual("<--autogenerate>" in recorded, autogenerate)
                self.assertNotIn("docker", recorded)
                self.assertIn("<--no-env-file>", recorded)

    def test_legacy_revision_cli_options_remain_supported(self) -> None:
        result = self.invoke(
            "host",
            "revision",
            "--message",
            "legacy migration",
            "--autogenerate",
            "--yes",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = self.log.read_text(encoding="utf-8")
        self.assertIn("<revision>", recorded)
        self.assertIn("<--message> <legacy migration>", recorded)
        self.assertIn("<--autogenerate>", recorded)

    def test_write_actions_remain_host_only_and_require_confirmation(self) -> None:
        for target, action in (
            ("compose", "blank-revision"),
            ("compose", "autogenerate-revision"),
        ):
            result = self.invoke(target, action, "--message", "unsafe", "--yes")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.log.exists())
        result = self.invoke("host", "upgrade")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
