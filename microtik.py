#!/usr/bin/python3

import sys
import argparse
import configparser
import paramiko
import ipaddress

def mikrotik_command(ssh, command):
    ssh.send(command + "\r\n")
    buff = ''
    while not buff.endswith('> '):
        resp = ssh.recv(4096).decode('utf-8', errors='ignore')
        buff += resp
        if '-- more --' in buff:
            ssh.send(' ')
            buff = buff.replace('-- more --', '')
    return buff


def is_valid_ip_or_network(line):
    try:
        ipaddress.ip_network(line, strict=False)
        return True
    except ValueError:
        return False

def read_addresses(source):
    addresses = []
    for line in source:
        clean = line.split('#', 1)[0].strip()
        if not clean:
            continue
        if is_valid_ip_or_network(clean):
            addresses.append(clean)
        else:
            print(f"Skipping invalid line: {line.strip()}", file=sys.stderr)
    return addresses

def main():
    parser = argparse.ArgumentParser(description='Update MikroTik address list from a file or stdin.')
    parser.add_argument('filename', nargs='?', help='File with IP/networks (one per line, supports # comments). If omitted, reads from stdin.')
    parser.add_argument('-c', '--config', default='microtik.cfg', help='Config file with router connection info (default: microtik.cfg)')
    args = parser.parse_args()

    # Parse config
    config = configparser.ConfigParser()
    if not config.read(args.config):
        print(f"Error: config file '{args.config}' not found or invalid.", file=sys.stderr)
        sys.exit(1)
    try:
        host = config.get('router', 'host')
        user = config.get('router', 'user')
        password = config.get('router', 'password')
        address_list = config.get('router', 'address_list')
    except configparser.NoOptionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Read addresses from file or stdin
    if args.filename:
        with open(args.filename, 'r') as f:
            addresses = read_addresses(f)
    else:
        print("Reading addresses from stdin... (Ctrl-D to end on Linux/macOS, Ctrl-Z on Windows)")
        addresses = read_addresses(sys.stdin)

    if not addresses:
        print("No valid addresses found. Exiting.", file=sys.stderr)
        sys.exit(0)

    # Start SSH session
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(host, username=user, password=password, look_for_keys=False, allow_agent=False)
        print("SSH connected.")

        ssh = client.invoke_shell()
        ssh.recv(4096)  # Welcome message
        mikrotik_command(ssh, '')

        remove_cmd = f'/ip firewall address-list remove [find list={address_list}]'
        print(f"Removing all entries from address list '{address_list}'...")
        mikrotik_command(ssh, remove_cmd)

        for addr in addresses:
            add_cmd = f'/ip firewall address-list add list={address_list} address={addr}'
            print(f"Adding {addr} to address list '{address_list}'...")
            mikrotik_command(ssh, add_cmd)

        ssh.send('quit\n')

    finally:
        client.close()
        print("SSH session closed.")

if __name__ == "__main__":
    main()
