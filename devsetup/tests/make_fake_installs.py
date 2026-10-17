#!/usr/bin/env python3
"""Build fake World of Warcraft installs for test_link_scripts.sh (no game client needed).

usage: python3 make_fake_installs.py DEST

DEST must not exist yet. For every scenario below it writes a macOS tree and a Windows tree:

  DEST/<scenario>/mac/Applications/World of Warcraft/...       (+ Users/Shared/Battle.net/Agent/product.db)
  DEST/<scenario>/win/C/Program Files (x86)/World of Warcraft/... (+ C/ProgramData/Battle.net/Agent/product.db)

Each install has a .build.info (BPSV, CRLF, as the Battle.net agent writes it), one folder per
product with a .flavor.info (the product code) and, where the client "has run", WTF/Config.wtf
with "SET lastAddonVersion". product.db is a protobuf with the field numbers WowUp decodes
(product install = field 1 {2: product code, 3: {1: install path, 13: game subfolder}, 6: family}).
The link scripts read these trees through their test hooks WOW_DEVSETUP_OS and
WOW_DEVSETUP_TEST_PREFIX. DEST/dev/Tx_Bags is a dev checkout to link.

Standard library only; Python 3.8+.
"""
import os
import sys

# scenario -> (description, [(product, folder, version, lastAddonVersion or None)], flavor_info, product_db)
SCENARIOS = {
    "S1": ("before the stress test: retail and the Forever beta", [
        ("wow", "_retail_", "12.1.5.70391", "120105"),
        ("wow_classic_beta", "_classic_beta_", "1.60.1.70425", "16001"),
    ], True, True),
    "S2": ("Oct 16-19: the Forever beta and the stress test (product wowf, new folder) both installed", [
        ("wow", "_retail_", "12.1.5.70391", "120105"),
        ("wow_classic_beta", "_classic_beta_", "1.60.1.70425", "16001"),
        ("wowf", "_forever_", "1.60.1.70245", None),
    ], True, True),
    "A": ("launch, layout A, the old beta still installed", [
        ("wow", "_retail_", "12.1.5.70391", "120105"),
        ("wow_classic_beta", "_classic_beta_", "1.60.1.70425", "16001"),
        ("wowf", "_forever_", "1.60.2.71000", "16002"),
    ], True, True),
    "A2": ("launch, layout A, the beta uninstalled", [
        ("wow", "_retail_", "12.1.5.70391", "120105"),
        ("wowf", "_forever_", "1.60.2.71000", None),
    ], True, True),
    "B": ("layout B: Forever inside the retail product (shared _retail_), stale beta still installed", [
        ("wow", "_retail_", "12.1.7.70500", "16001"),
        ("wow_classic_beta", "_classic_beta_", "1.60.1.70425", "16001"),
    ], True, True),
    "C": ("layout C: the beta slot carries the live game", [
        ("wow", "_retail_", "12.1.5.70391", "120105"),
        ("wow_classic_beta", "_classic_beta_", "1.60.2.71000", None),
    ], True, True),
    "R": ("the beta slot reused for another game, Forever in its own folder", [
        ("wow", "_retail_", "12.1.5.70391", "120105"),
        ("wow_classic_beta", "_classic_beta_", "2.5.7.72000", "16001"),
        ("wowf", "_forever_", "1.60.2.71000", "16002"),
    ], True, True),
    "U": ("degraded: no .flavor.info, no product.db; the new folder never launched", [
        ("wow", "_retail_", "12.1.5.70391", "120105"),
        ("wow_classic_beta", "_classic_beta_", "1.60.1.70425", "16001"),
        ("wowf", "_forever_", "1.60.1.70245", None),
    ], False, False),
}

BUILD_INFO_HEADER = "Branch!STRING:0|Active!DEC:1|Build Key!HEX:16|CDN Key!HEX:16|Version!STRING:0|Product!STRING:0"


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def field(num, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return varint((num << 3) | 2) + varint(len(data)) + data


def product_db(install_path, products):
    db = b""
    for code, folder, _, _ in products:
        settings = field(1, install_path) + field(2, "us") + field(13, folder)
        db += field(1, field(1, code) + field(2, code) + field(3, settings) + field(6, "wow"))
    # a non-WoW product the readers must skip
    db += field(1, field(1, "pro") + field(2, "pro") + field(3, field(1, install_path + "-other")) + field(6, "pro"))
    return db + field(7, "agent")


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def build_install(root, products, flavor_info):
    rows = [BUILD_INFO_HEADER] + ["us|1|aa|bb|%s|%s" % (version, code) for code, _, version, _ in products]
    write(os.path.join(root, ".build.info"), "\r\n".join(rows) + "\r\n")
    for code, folder, _, last in products:
        d = os.path.join(root, folder)
        os.makedirs(d, exist_ok=True)
        if flavor_info:
            write(os.path.join(d, ".flavor.info"), "Product Flavor!STRING:0\r\n%s\r\n" % code)
        if last:
            write(os.path.join(d, "WTF", "Config.wtf"), 'SET locale "enUS"\r\nSET lastAddonVersion "%s"\r\n' % last)
            os.makedirs(os.path.join(d, "Interface", "AddOns"), exist_ok=True)


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    dest = os.path.abspath(argv[1])
    if not argv[1] or os.path.exists(dest):
        print("refusing: DEST must be a new folder: %r" % argv[1], file=sys.stderr)
        return 2
    for name, (_, products, flavor_info, with_db) in SCENARIOS.items():
        mac = os.path.join(dest, name, "mac")
        build_install(os.path.join(mac, "Applications", "World of Warcraft"), products, flavor_info)
        win = os.path.join(dest, name, "win")
        build_install(os.path.join(win, "C", "Program Files (x86)", "World of Warcraft"), products, flavor_info)
        if with_db:
            write(os.path.join(mac, "Users", "Shared", "Battle.net", "Agent", "product.db"),
                  product_db("/Applications/World of Warcraft", products))
            write(os.path.join(win, "C", "ProgramData", "Battle.net", "Agent", "product.db"),
                  product_db("C:\\Program Files (x86)\\World of Warcraft", products))
    addon = os.path.join(dest, "dev", "Tx_Bags")
    write(os.path.join(addon, "Tx_Bags.toc"), "## Interface: 16001\n## Title: Tx Bags\nCore.lua\n")
    write(os.path.join(addon, "Core.lua"), 'print("dev checkout")\n')
    for name, (desc, _, _, _) in SCENARIOS.items():
        print("%-3s %s" % (name, desc))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
