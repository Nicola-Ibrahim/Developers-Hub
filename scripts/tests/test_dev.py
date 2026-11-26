"""Exercise Bash routing and cache boundaries with an isolated mocked Docker CLI."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]


class DeveloperCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("scripts/helpers", "scripts/shell", "backend", "frontend", "bin"):
            (self.root / name).mkdir(parents=True)
        shutil.copy(SOURCE / "dev.sh", self.root / "scripts/dev.sh")
        shutil.copy(SOURCE.parent / "compose.yaml", self.root / "compose.yaml")
        for name in (
            "menu.sh",
            "docker.sh",
            "cleanup.sh",
            "dev-docker.sh",
            "native.sh",
            "database.sh",
        ):
            source = SOURCE / "shell" / name
            if source.exists():
                shutil.copy(source, self.root / "scripts/shell" / name)
        shutil.copy(
            SOURCE / "helpers/init_env.py", self.root / "scripts/helpers/init_env.py"
        )
        self.log = self.root / "docker.calls"
        self.command_log = self.root / "commands.calls"
        mock = self.root / "bin/docker"
        mock.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_TEST_LOG"\n'
            'if [ "$1" = info ]; then exit "${DOCKER_TEST_INFO:-0}"; fi\n'
            'if [ "$1" = volume ]; then exit 0; fi\nexit 0\n'
        )
        mock.chmod(0o755)
        for name in ("uv", "npm", "python3"):
            command = self.root / "bin" / name
            if name == "python3":
                command.write_text(
                    '#!/bin/sh\nprintf "python3 %s\\n" "$*" >> "$COMMAND_TEST_LOG"\n'
                    'exit "${PYTHON_TEST_EXIT:-0}"\n'
                )
            else:
                command.write_text(
                    f'#!/bin/sh\nprintf "{name} %s\\n" "$*" >> "$COMMAND_TEST_LOG"\n'
                    f'exit "${{{name.upper()}_TEST_EXIT:-0}}"\n'
                )
            command.chmod(0o755)
        db_menu = self.root / "scripts/db.sh"
        db_menu.write_text('#!/bin/sh\nprintf "db %s\\n" "$*" >> "$COMMAND_TEST_LOG"\n')
        self.env = dict(
            os.environ,
            PATH=str(self.root / "bin") + os.pathsep + os.environ["PATH"],
            DOCKER_TEST_LOG=str(self.log),
            COMMAND_TEST_LOG=str(self.command_log),
            DOCKER_HOST="unix:///tmp/mock-docker.sock",
            DOCKER_CONTEXT="",
        )

    def run_command(self, *args, **environment):
        return subprocess.run(
            ["bash", str(self.root / "scripts/dev.sh"), *args],
            check=False,
            cwd="/",
            env=dict(self.env, **environment),
            text=True,
            capture_output=True,
        )

    def test_help_and_invalid_options_have_no_docker_or_env_effects(self):
        self.assertEqual(self.run_command("help").returncode, 0)
        self.assertEqual(self.run_command("up", "--unknown").returncode, 2)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.root / "backend/.env").exists())

    def test_unreachable_daemon_does_not_generate_credentials(self):
        self.assertNotEqual(self.run_command("up", DOCKER_TEST_INFO="1").returncode, 0)
        self.assertFalse((self.root / "backend/.env").exists())

    def test_remote_daemon_is_refused_for_start_and_stop(self):
        for action in ("up", "down", "status"):
            self.assertNotEqual(
                self.run_command(
                    action, DOCKER_HOST="tcp://remote.invalid:2375"
                ).returncode,
                0,
            )
        self.assertFalse(self.log.exists())
        self.assertFalse((self.root / "backend/.env").exists())

    def test_up_and_down_use_core_compose_and_preserve_volumes(self):
        result = self.run_command("up")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "--project-name devops-hub up --build -d --wait --remove-orphans",
            self.log.read_text(),
        )
        self.assertEqual(self.run_command("down").returncode, 0)
        self.assertIn(
            "--project-name devops-hub down --remove-orphans",
            self.log.read_text(),
        )
        self.assertNotIn("--volumes", self.log.read_text())

    def test_removed_worker_flags_are_rejected_before_docker_or_env(self):
        for args in (("up", "--resources"), ("up", "--application-delivery")):
            self.assertEqual(self.run_command(*args).returncode, 2)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.root / "backend/.env").exists())

    def test_compose_contract_has_exact_five_services_without_profiles(self):
        compose = (self.root / "compose.yaml").read_text()
        services = re.search(r"(?ms)^services:\n(.*?)(?=^[^ \n]|\Z)", compose)
        self.assertIsNotNone(services)
        names = re.findall(
            r"^  ([a-z][a-z0-9-]*):\s*$", services.group(1), re.MULTILINE
        )
        self.assertEqual(names, ["postgres", "migrate", "api", "opa", "frontend"])
        self.assertNotRegex(compose, r"(?m)^\s*profiles:")
        self.assertIn("control_plane_data:/var/lib/postgresql/data", compose)
        self.assertIn("name: devops-hub", compose)
        self.assertIn("./ops/policies:/policies:ro", compose)
        self.assertIn("data.devops.authorization.decision.policy_revision", compose)
        self.assertIn("service_completed_successfully", compose)
        self.assertIn("127.0.0.1:8000:8000", compose)
        self.assertIn("127.0.0.1:3000:3000", compose)

    def test_clean_is_preview_first_and_refuses_symlink(self):
        cache = self.root / "backend/.pytest_cache"
        cache.mkdir()
        sentinel = cache / "sentinel"
        sentinel.write_text("cache")
        self.assertEqual(self.run_command("clean").returncode, 0)
        self.assertTrue(sentinel.exists())
        self.assertEqual(self.run_command("clean", "--apply").returncode, 0)
        self.assertFalse(cache.exists())
        cache.symlink_to(self.root / "frontend", target_is_directory=True)
        self.assertNotEqual(self.run_command("clean", "--apply").returncode, 0)
        self.assertTrue((self.root / "frontend").is_dir())
        self.assertEqual(self.run_command("logs", "arbitrary").returncode, 2)
        for service in ("worker", "application-worker"):
            self.assertEqual(self.run_command("logs", service).returncode, 2)

    def test_no_arguments_is_help_without_tty(self):
        result = self.run_command()
        self.assertEqual(result.returncode, 0)
        self.assertIn("Usage:", result.stdout)
        self.assertFalse(self.command_log.exists())

    def test_menu_retries_invalid_then_returns_on_back_and_eof_quits(self):
        result = subprocess.run(
            ["bash", str(self.root / "scripts/dev.sh"), "menu"],
            cwd="/",
            env=self.env,
            input="99\nb\n",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Invalid choice", result.stderr)
        result = subprocess.run(
            ["bash", str(self.root / "scripts/dev.sh"), "menu"],
            cwd="/",
            env=self.env,
            input="",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)

    def test_menu_routes_native_frontend_and_database_and_survives_failure(self):
        # Select native frontend; mocked npm exits unsuccessfully, then Back exits submenu.
        result = subprocess.run(
            ["bash", str(self.root / "scripts/dev.sh"), "menu"],
            cwd="/",
            env=dict(self.env, NPM_TEST_EXIT="9"),
            input="2\n2\nb\nb\n",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.command_log.read_text()
        self.assertIn("npm run dev -- --hostname 127.0.0.1", calls)
        self.assertIn("Action failed (exit 1)", result.stderr)
        self.command_log.unlink()
        result = subprocess.run(
            ["bash", str(self.root / "scripts/dev.sh"), "menu"],
            cwd="/",
            env=self.env,
            input="3\n2\n2\nb\nb\n",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("alembic history --verbose", self.command_log.read_text())

    def test_integrated_database_quit_exits_dev_but_back_returns(self):
        for data in ("3\nq\n", "3\n2\n7\nq\n"):
            result = subprocess.run(
                ["bash", str(self.root / "scripts/dev.sh"), "menu"],
                input=data,
                text=True,
                capture_output=True,
                env=self.env,
                check=False,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr.count("DEVOPS HUB | Development"), 1)
            self.assertFalse(self.log.exists())
        result = subprocess.run(
            ["bash", str(self.root / "scripts/dev.sh"), "menu"],
            input="3\nb\nq\n",
            text=True,
            capture_output=True,
            env=self.env,
            check=False,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.count("DEVOPS HUB | Development"), 2)

    def test_native_backend_command_is_pinned_and_no_dependency_mutation(self):
        helper = self.root / "scripts/helpers/local_database.py"
        helper.write_text("pass\n")
        result = subprocess.run(
            ["bash", str(self.root / "scripts/dev.sh"), "menu"],
            cwd="/",
            env=self.env,
            input="2\n1\nb\nb\n",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.command_log.read_text()
        self.assertIn("python3 ", calls)
        self.assertIn(
            "uv run --offline --frozen --no-sync --no-env-file fastapi dev --host 127.0.0.1 --port 8000",
            calls,
        )
        self.assertNotIn("uv sync --frozen", calls)

    def test_docker_menu_starts_core_services_and_returns_with_back(self):
        result = subprocess.run(
            ["bash", str(self.root / "scripts/dev.sh"), "menu"],
            cwd="/",
            env=self.env,
            input="1\n1\nb\nb\n",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "--file "
            + str(self.root / "compose.yaml")
            + " --project-directory "
            + str(self.root)
            + " --project-name devops-hub up --build -d --wait --remove-orphans",
            self.log.read_text(),
        )
        self.assertNotIn("profile", result.stderr.lower())
        self.assertNotIn("worker startup", result.stdout.lower())

    def test_interactive_start_and_nested_quit_exits(self):
        result = subprocess.run(
            ["bash", str(self.root / "scripts/dev.sh"), "menu"],
            cwd="/",
            env=self.env,
            input="1\n1\nb\nb\n",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("up --build -d --wait --remove-orphans", self.log.read_text())
        self.log.unlink()
        result = subprocess.run(
            ["bash", str(self.root / "scripts/dev.sh"), "menu"],
            cwd="/",
            env=self.env,
            input="1\nq\n",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())

    def test_direct_native_routes_are_available(self):
        self.assertEqual(self.run_command("frontend").returncode, 0)
        self.assertIn(
            "npm run dev -- --hostname 127.0.0.1", self.command_log.read_text()
        )


if __name__ == "__main__":
    unittest.main()
