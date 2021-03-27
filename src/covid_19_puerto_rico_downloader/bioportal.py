import argparse
import bz2
from datetime import datetime
import ijson
import json
import logging
import pathlib
import pyarrow
import pyarrow.json
import pyarrow.parquet
import requests
import shutil
import subprocess


BIOPORTAL_ENDPOINTS = {
    'grouped-by-collected-date':
        'https://BioPortal.salud.gov.pr/api/administration/reports/cases/grouped-by-collected-date',
#    'minimal-info-unique-tests':
#        'https://bioportal.salud.gov.pr/api/administration/reports/minimal-info-unique-tests',
#    'orders-basic':
#        'https://bioportal.salud.gov.pr/api/administration/reports/orders/basic'
}


def process_arguments():
    parser = argparse.ArgumentParser(description='Download Bioportal data sets')
    parser.add_argument('--s3-sync-dir', type=str, required=True,
                        help='Directory to which to deposit the output files for sync')
    return parser.parse_args()

def bioportal():
    """Entry point for Bioportal download code."""
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    args = process_arguments()
    Bioportal(args).run()


class Bioportal():
    """Downloader for Puerto Rico Department of Health Bioportal API"""
    def __init__(self, args):
        self.args = args
        self.s3_sync_dir = pathlib.Path(args.s3_sync_dir)
        self.bioportal_sync_dir = pathlib.Path(f'{self.s3_sync_dir}/bioportal')

    def run(self):
        self.make_directory_structure()
        now = datetime.utcnow()
        logging.info("Using downloadedAt = %s", now.isoformat())
        for key, url in BIOPORTAL_ENDPOINTS.items():
            self.process_endpoint(key, url, now)

    def make_directory_structure(self):
        """Ensure all of the required directories exist."""
        self.s3_sync_dir.mkdir(exist_ok=True)
        self.bioportal_sync_dir.mkdir(exist_ok=True)

    def make_destination_dir(self, key):
        destination = pathlib.Path(f'{self.bioportal_sync_dir}/{key}')
        destination.mkdir(exist_ok=True)
        return destination


    def process_endpoint(self, key, url, now):
        jsonfile = self.download_json(key, url, now)
        jsonlfile = f'{jsonfile}l'
        self.convert_to_jsonl(jsonfile, jsonlfile, now)
        jsonfile = self.compress_file(jsonfile)
        jsonlfile = self.compress_file(jsonlfile)
        parquetfile = f'{key}_{now.isoformat()}.parquet'
        # FIXME: fails because of colons in filename timestamp
        # self.convert_to_parquet(jsonlfile, parquetfile)

    def download_json(self, key, url, now):
        logging.info('Downloading %s from %s', key, url)
        r = requests.get(url, headers={'Accept-Encoding': 'gzip'})
        outpath = f'{key}_{now.isoformat()}.json'
        with open(outpath, 'wb') as fd:
            for chunk in r.iter_content(chunk_size=128):
                fd.write(chunk)
        return outpath

    def compress_file(self, path):
        logging.info('Compressing %s', path)
        subprocess.run(['bzip2', '-f', '-9', path])
        return f'{path}.bz2'

    def convert_to_jsonl(self, jsonfile, outpath, now):
        """Convert the single-object JSON output from Bioportal to newline-delimited.
        We also add a `downloadedAt` field to the records."""
        logging.info('Converting %s to jsonl...', jsonfile)
        now_str = now.isoformat()
        with open(jsonfile) as data:
            with open(outpath, 'w') as out:
                for record in ijson.items(data, prefix='item'):
                    record['downloadedAt'] = now_str
                    json.dump(record, out, allow_nan=False, separators=(',', ':'))
                    out.write('\n')

    def convert_to_parquet(self, jsonlfile, outpath):
        logging.info('Converting %s to Parquet...', jsonlfile)
        # FIXME: fails because of colons in filename timestamps
        table = pyarrow.json.read_json(jsonlfile)
        pyarrow.parquet.write_table(table, outpath)