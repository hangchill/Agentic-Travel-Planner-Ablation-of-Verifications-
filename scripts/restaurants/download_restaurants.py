"""Download the canonical Kaggle dataset, reusing an existing raw CSV."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT/'data/raw/restaurants/google_maps'
RAW_FILE = RAW_DIR/'google_maps_restaurants(cleaned).csv'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh',action='store_true')
    args=parser.parse_args()
    if RAW_FILE.exists() and not args.refresh:
        print(f'Using cached canonical source: {RAW_FILE}')
        return
    RAW_DIR.mkdir(parents=True,exist_ok=True)
    subprocess.run(['kaggle','datasets','download','beridzeg45/nyc-restaurants','-p',str(RAW_DIR),'--unzip'],check=True)
    if not RAW_FILE.exists():raise FileNotFoundError('Expected canonical CSV was not downloaded; review source schema')
    print(f'Canonical source downloaded to {RAW_DIR}')


if __name__=='__main__':main()
