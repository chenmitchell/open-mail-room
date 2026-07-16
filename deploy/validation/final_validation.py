#!/usr/bin/env python3
"""Final validation of all deployment files."""

import sys
import os

# Add YAML validation
try:
    import yaml
    yaml_available = True
except ImportError:
    yaml_available = False
    print("Warning: PyYAML not installed, skipping YAML validation")

def validate_yaml_file(filepath):
    """Validate YAML file."""
    if not yaml_available:
        return True, "YAML validator not available"

    try:
        with open(filepath, 'r') as f:
            yaml.safe_load(f)
        return True, None
    except yaml.YAMLError as e:
        return False, f"YAML Error: {e}"
    except Exception as e:
        return False, f"Error: {e}"

def validate_shell_file(filepath):
    """Basic shell script validation."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Check shebang
        if not content.startswith('#!/bin/bash'):
            return False, "Missing #!/bin/bash"

        # Count brackets
        open_parens = content.count('(')
        close_parens = content.count(')')
        if open_parens != close_parens:
            return False, f"Bracket mismatch: ( {open_parens}, ) {close_parens}"

        return True, None
    except Exception as e:
        return False, f"Error: {e}"

def main():
    files = [
        ('C:\\Users\\test\\Downloads\\openmailroom\\deploy\\docker-compose.yml', 'yaml'),
        ('C:\\Users\\test\\Downloads\\openmailroom\\config\\branding.yaml', 'yaml'),
        ('C:\\Users\\test\\Downloads\\openmailroom\\.github\\workflows\\ci.yml', 'yaml'),
        ('C:\\Users\\test\\Downloads\\openmailroom\\deploy\\deploy.sh', 'shell'),
        ('C:\\Users\\test\\Downloads\\openmailroom\\deploy\\selfsigned.sh', 'shell'),
    ]

    print("=" * 60)
    print("OpenMailroom Deployment Files Validation")
    print("=" * 60)
    print()

    all_passed = True

    for filepath, filetype in files:
        filename = filepath.split('\\')[-1]

        if not os.path.exists(filepath):
            print(f"✗ {filename} - FILE NOT FOUND")
            all_passed = False
            continue

        if filetype == 'yaml':
            passed, error = validate_yaml_file(filepath)
        else:
            passed, error = validate_shell_file(filepath)

        status = "✓" if passed else "✗"
        print(f"{status} {filename}")
        if error:
            print(f"  └─ {error}")
            all_passed = False

    print()
    print("=" * 60)

    if all_passed:
        print("✓ All validation checks PASSED")
        print("=" * 60)
        return 0
    else:
        print("✗ Some validation checks FAILED")
        print("=" * 60)
        return 1

if __name__ == '__main__':
    sys.exit(main())
