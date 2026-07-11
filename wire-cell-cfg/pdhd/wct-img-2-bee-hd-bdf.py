#!/usr/bin/env python
#
# Convert per-anode (rec, bdf) cluster file pairs into Bee json and pack
# them into upload.zip. Supports any subset of the 4 protoDUNE-HD anodes
# (0-3), unlike the original which only ever handled a single hardcoded
# anode pair.
#
# Odd/even anodes drift in opposite directions, so --speed/--x0 sign
# flips with anode parity (same convention as wct-img-2-bee-hd.py:
# apa0/apa2 negative, apa1/apa3 positive).
#
# Usage:
#   python wct-img-2-bee-hd-bdf.py --pair ANODE REC BDF [--pair ANODE REC BDF ...]
#
# Example (anodes 0 and 1):
#   python wct-img-2-bee-hd-bdf.py \
#       --pair 0 clusters-apa-0.tar.gz clusters-apa-bdf-0.tar.gz \
#       --pair 1 clusters-apa-1.tar.gz clusters-apa-bdf-1.tar.gz

import argparse
import os

DENSITY = 1

def convert(anode, fp, tag):
    sign = '' if anode % 2 else '-'
    outname = 'data/0/0-apa%d-%s.json' % (anode, tag)
    cmd = 'wirecell-img bee-blobs -g protodunehd -s uniform -d %f --speed "%s1.6*mm/us" --t0 "250*us" --x0 "%s358*cm" -o %s %s' % (
        DENSITY, sign, sign, outname, fp)
    print(cmd)
    os.system(cmd)


def main(pairs):
    if os.path.exists('data/0'):
        print('found old data, removing ...')
        os.system('rm -rf data')
    if os.path.exists('upload.zip'):
        os.system('rm -f upload.zip')
    os.system('mkdir -p data/0')

    for anode, rec_fp, bdf_fp in pairs:
        convert(anode, rec_fp, 'rec')
        convert(anode, bdf_fp, 'bdf')

    os.system('zip -r upload data')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert per-anode rec/bdf cluster files into a Bee upload.zip.")
    parser.add_argument(
        '--pair', nargs=3, action='append', required=True,
        metavar=('ANODE', 'REC', 'BDF'),
        help='anode index (0-3) and its rec/bdf cluster files; repeat for multiple anodes')
    args = parser.parse_args()

    pairs = [(int(anode), rec_fp, bdf_fp) for anode, rec_fp, bdf_fp in args.pair]
    main(pairs)
