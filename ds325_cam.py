#!/usr/bin/env python3
"""Compatibility launcher for the Django-based DS325 Studio."""

import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ds325_project.settings")

    from django.core.management import execute_from_command_line

    args = [sys.argv[0], "runserver"]
    if len(sys.argv) == 1:
        args.append("0.0.0.0:8000")
    execute_from_command_line([*args, *sys.argv[1:]])
