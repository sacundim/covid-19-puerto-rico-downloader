"""Download data from the Puerto Rico Department of Health Bioportal API."""

import argparse
import copy
from datetime import datetime
import json
import json_stream
from json_stream.dump import JSONStreamEncoder
import logging
from pyarrow import json as arrow_json
import pyarrow
import pyarrow.parquet as parquet
from pytz import timezone
import requests
import subprocess


BIOPORTAL_URL = "https://bioportal.salud.pr.gov/api/administration/reports"
DEATHS_ENDPOINT = f"{BIOPORTAL_URL}/deaths/summary"
TESTS_ENDPOINT = f"{BIOPORTAL_URL}/minimal-info-unique-tests"
ORDERS_ENDPOINT = f"{BIOPORTAL_URL}/orders/basic"


def process_arguments():
    parser = argparse.ArgumentParser(description='Download Bioportal COVID-19 data sets')
    parser.add_argument('--s3-sync-dir', type=str, required=True,
                        help='Directory to which to deposit the output files for sync')
    return parser.parse_args()

def bioportal_download():
    """Entry point for Bioportal download code."""
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    args = process_arguments()
    now = datetime.now(tz=timezone('America/Puerto_Rico'))
    logging.info('Now = %s', now.isoformat())
    deaths_download(now, args)

def deaths_download(now, args):
    json_path = make_filename('deaths', now, 'json')
    jsonl_path = make_filename('deaths', now, 'jsonl')
    parquet_path = make_filename('deaths', now, 'parquet')

    download_url(DEATHS_ENDPOINT, json_path)
    json2jsonl(json_path, jsonl_path, now)
    compress_file(json_path)
    table = arrow_json.read_json(jsonl_path)
    parquet.write_table(table, parquet_path,
                        filesystem=pyarrow.fs.LocalFileSystem(),
                        compression='GZIP',
                        row_group_size=10_000_000)

def make_filename(basename, now, extension):
    return f'{basename}_{now.isoformat()}.{extension}'

def download_url(url, outpath):
    logging.info('Downloading %s from %s', outpath, url)
    r = requests.get(url)
    with open(outpath, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=128):
            fd.write(chunk)

def json2jsonl(inputfile, outputfile, downloadedAt):
    downloadedAt = downloadedAt.isoformat()
    with open(inputfile, 'r') as input:
        with open(outputfile, 'w') as output:
            data = json_stream.load(input)
            for record in data.persistent():
#                copied = copy.copy(record)
#                copied['downloadedAt'] = downloadedAt
                output.write(json.dumps(record, default=json_stream.dump.default))
                output.write('\n')

def compress_file(file):
    logging.info("Compressing file: %s", file)
    subprocess.run(['bzip2', '-f', '-9', file])
    return f"{file}.bz2"

