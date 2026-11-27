"""Validation shared by application delivery commands."""

import re

APP_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
DIGEST = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:@-]{0,250}@sha256:[a-f0-9]{64}\Z")
IDEMPOTENCY = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
