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



#    'minimal-info-unique-tests':
#        'https://bioportal.salud.gov.pr/api/administration/reports/minimal-info-unique-tests',
#    'orders-basic':
#        'https://bioportal.salud.gov.pr/api/administration/reports/orders/basic'


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

        # Without this `filesystem` nonsense (used below), PyArrow fails if there's
        # colons in filename timestamps
        self.filesystem = pyarrow.fs.LocalFileSystem()

    def run(self):
        self.make_directory_structure()
        now = datetime.utcnow()
        logging.info("Using downloadedAt = %s", now.isoformat())
        for endpoint in BIOPORTAL_ENDPOINTS:
            self.process_endpoint(endpoint, now)
        logging.info('All downloads done!')

    def make_directory_structure(self):
        """Ensure all of the required directories exist."""
        self.s3_sync_dir.mkdir(exist_ok=True)
        self.bioportal_sync_dir.mkdir(exist_ok=True)


    def process_endpoint(self, endpoint, now):
        jsonfile = self.download_json(endpoint, now)
        jsonlfile = f'{jsonfile}l'
        self.convert_to_jsonl(jsonfile, jsonlfile, now)
        jsonfile = self.compress_file(jsonfile)
        jsonlfile = self.compress_file(jsonlfile)
        parquetfile = endpoint.make_filename(now, "parquet")
        self.convert_to_parquet(jsonlfile, parquetfile)

        self.move_to_sync_dir(endpoint, now, "json", "json.bz2")
        self.move_to_sync_dir(endpoint, now, "jsonl", "jsonl.bz2")
        self.move_to_sync_dir(endpoint, now, "parquet", "parquet")


    def move_to_sync_dir(self, endpoint, now, format, extension):
        destination = endpoint.make_destination_dir(self.bioportal_sync_dir, format)
        filename = endpoint.make_filename(now, extension)
        logging.info('Moving %s to %s/', filename, destination)
        shutil.move(filename, f'{destination}/{filename}')

    def download_json(self, endpoint, now):
        logging.info('Downloading %s from %s', endpoint.name, endpoint.url)
        r = requests.get(endpoint.url, headers={'Accept-Encoding': 'gzip'})
        jsonfile = endpoint.make_filename(now, "json")
        with open(jsonfile, 'wb') as fd:
            for chunk in r.iter_content(chunk_size=128):
                fd.write(chunk)
        return jsonfile

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
        table = pyarrow.json.read_json(jsonlfile)
        # Without this `filesystem` nonsense, PyArrow fails if there's colons
        # in filename timestamps
        pyarrow.parquet.write_table(table, outpath, filesystem=self.filesystem)

class Endpoint():
    def __init__(self, name, version, url):
        self.name = name
        self.version = version
        self.url = url

    def make_destination_dir(self, bioportal_sync_dir, format):
        destination = pathlib.Path(f'{bioportal_sync_dir}/bioportal/{self.name}/{format}_{self.version}')
        destination.mkdir(exist_ok=True, parents=True)
        return destination

    def make_filename(self, now, extension):
        return f'{self.name}_{now.isoformat()}.{extension}'

BIOPORTAL_ENDPOINTS = [
    Endpoint(
        'grouped-by-collected-date', 'v1',
        'https://BioPortal.salud.gov.pr/api/administration/reports/cases/grouped-by-collected-date'
    )
]
