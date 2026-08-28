#!/usr/bin/env python3

import json
import sys
import argparse
import os


def parse_input_file(filename):
    """
    Parse inventory_def.txt where each line is:

    ansible_hostname ip ansible_user group hostname ssh_port

    Example:
    hpc-master01 192.168.1.10 root hpc_master master01 4411
    """

    groups = {}
    hostvars = {}

    if not os.path.exists(filename):
        print(f"Error: Input file '{filename}' not found.", file=sys.stderr)
        sys.exit(1)

    with open(filename, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split()

            # Expecting 6 columns
            if len(parts) != 6:
                print(
                    f"Warning: Invalid line {lineno} in {filename}: {line}",
                    file=sys.stderr,
                )
                continue

            ansible_hostname, ip, user, group, hostname, ssh_port = parts

            try:
                ssh_port = int(ssh_port)
            except ValueError:
                print(
                    f"Warning: Invalid SSH port on line {lineno}. Using default port 22.",
                    file=sys.stderr,
                )
                ssh_port = 22

            if group not in groups:
                groups[group] = {
                    "hosts": [],
                    "vars": {}
                }

            groups[group]["hosts"].append(ansible_hostname)

            hostvars[ansible_hostname] = {
                "ansible_host": ip,
                "ansible_user": user,
                "ansible_port": ssh_port,
                "hostname": hostname,
                "group": group,
            }

    return groups, hostvars


def generate_inventory(input_file):
    groups, hostvars = parse_input_file(input_file)
    inventory = {
        "_meta": {
            "hostvars": hostvars
        }
    }
    inventory.update(groups)
    return inventory


def main():
    parser = argparse.ArgumentParser(
        description="Dynamic Inventory Generator for Ansible"
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="Output full inventory in JSON",
    )

    parser.add_argument(
        "--host",
        help="Output details for a specific host",
    )

    parser.add_argument(
        "--input-file",
        default="inventory_def.txt",
        help="Path to input inventory file (default: inventory_def.txt)",
    )

    args = parser.parse_args()

    if args.list:
        print(json.dumps(generate_inventory(args.input_file), indent=2))

    elif args.host:
        _, hostvars = parse_input_file(args.input_file)
        print(json.dumps(hostvars.get(args.host, {}), indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
