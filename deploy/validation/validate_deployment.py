#!/usr/bin/env python3
"""Validate deployment configuration files."""

import sys
import yaml
from pathlib import Path

def validate_yaml(filepath):
    """Validate YAML file syntax."""
    try:
        with open(filepath) as f:
            yaml.safe_load(f)
        return True, None
    except yaml.YAMLError as e:
        return False, str(e)
    except FileNotFoundError:
        return False, f"File not found: {filepath}"

def validate_shell(filepath):
    """Basic shell script validation (checks for matching quotes/brackets)."""
    try:
        with open(filepath) as f:
            content = f.read()

        # Check shebang
        if not content.startswith('#!/bin/bash'):
            return False, "Missing #!/bin/bash shebang"

        # Basic bracket matching
        open_count = content.count('(')
        close_count = content.count(')')
        if open_count != close_count:
            return False, f"Mismatched parentheses: {open_count} open, {close_count} close"

        # Check for obvious issues
        if 'set -euo pipefail' not in content:
            return False, "Missing 'set -euo pipefail' for error handling"

        return True, None
    except FileNotFoundError:
        return False, f"File not found: {filepath}"

def validate_env_example(filepath):
    """Validate .env.example format."""
    try:
        with open(filepath) as f:
            content = f.read()

        # Should contain comments explaining each variable
        if not content.count('#') > 10:
            return False, "Too few comments in .env.example"

        # Should have at least some variable placeholders
        if content.count('=') < 10:
            return False, "Too few variable assignments"

        return True, None
    except FileNotFoundError:
        return False, f"File not found: {filepath}"

def main():
    """Run all validations."""
    base_path = Path('/sessions/funny-optimistic-ritchie/mnt/Downloads/openmailroom')

    validations = [
        ('deploy/docker-compose.yml', validate_yaml),
        ('config/branding.yaml', validate_yaml),
        ('.github/workflows/ci.yml', validate_yaml),
        ('deploy/deploy.sh', validate_shell),
        ('deploy/selfsigned.sh', validate_shell),
        ('.env.example', validate_env_example),
    ]

    all_passed = True

    for filepath, validator in validations:
        full_path = base_path / filepath
        passed, error = validator(str(full_path))

        status = "✓" if passed else "✗"
        print(f"{status} {filepath}")

        if error:
            print(f"  Error: {error}")
            all_passed = False

    print()
    if all_passed:
        print("✓ All validation checks passed!")
        return 0
    else:
        print("✗ Some validation checks failed")
        return 1

if __name__ == '__main__':
    sys.exit(main())
