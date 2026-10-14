#!/usr/bin/env python3
"""Executa o ShareScreen direto da pasta do projeto."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sharescreen.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
