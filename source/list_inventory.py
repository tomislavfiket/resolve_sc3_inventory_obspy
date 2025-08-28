#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
List all stations and channels in an inventory file.
"""

from obspy import read_inventory
import argparse

def main():
    ap = argparse.ArgumentParser(description="List all stations in an inventory.")
    ap.add_argument("--inventory", required=True, help="Path to StationXML/SC3ML file")
    args = ap.parse_args()

    inv = read_inventory(args.inventory)

    for net in inv:
        print(f"Network: {net.code}")
        for sta in net.stations:
            print(f"  Station: {sta.code} "
                  f"(Lat={sta.latitude}, Lon={sta.longitude}, Elev={sta.elevation}) "
                  f"Start={sta.start_date}, End={sta.end_date}")
            for ch in sta.channels:
                print(f"    Channel: {ch.code}, Loc: {ch.location_code or ''}, "
                      f"SR={ch.sample_rate} Hz, "
                      f"Start={ch.start_date}, End={ch.end_date}")
        print()

if __name__ == "__main__":
    main()
