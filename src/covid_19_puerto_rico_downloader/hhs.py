import argparse
from csv2parquet import csv2parquet
import datetime
import json
import logging
import os
import os.path
import pathlib
import requests
import shutil
from sodapy import Socrata
import subprocess


def process_arguments():
    parser = argparse.ArgumentParser(description='Download HHS COVID-19 data sets')
    parser.add_argument('--socrata-app-token', type=str,
                        help='Socrata API App Token. '
                             'Not required but we get throttled without it. '
                             'This parameter takes precedence over --socrata-app-token-env-var.')
    parser.add_argument('--socrata-app-token-env-var', type=str,
                        help='Environment variable from which to get Socrata API App Token. '
                             'Not required but we get throttled without it. '
                             'The --socrata-app-token parameter takes precedence over this one.')
    parser.add_argument('--s3-sync-dir', type=str, required=True,
                        help='Directory to which to deposit the output files for sync')
    return parser.parse_args()


def hhs_download():
    """Entry point for HHS download code."""
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    args = process_arguments()
    healthdata_download(args)
    cdc_download(args)

def get_socrata_app_token(args):
    if args.socrata_app_token:
        logging.info("Using Socrata App Token from command line")
        return args.socrata_app_token
    elif args.socrata_app_token_env_var:
        env_var = args.socrata_app_token_env_var
        logging.info("Using Socrata App Token from environment variable %s", env_var)
        try:
            return os.environ[env_var]
        except e:
            logging.error('Environment variable %s not set', env_var)
            raise e
    else:
        logging.warning("No Socrata App Token. The API may throttle us.")
        return None


def healthdata_download(args):
    '''Download datasets hosted at healthdata.gov API endpoints'''
    datasets = [
        Asset('covid-19_community_profile_report_county', 'di4u-7yu6'),
        Asset('covid-19_diagnostic_lab_testing', 'j8mb-icvb'),
        Asset('estimated_icu', '7ctx-gtb7'),
        Asset('estimated_inpatient_all', 'jjp9-htie'),
        Asset('estimated_inpatient_covid', 'py8k-j5rq'),
        Asset('reported_hospital_utilization', '6xf2-c3ie'),
        Asset('reported_hospital_utilization_timeseries', 'g62h-syeh'),
        Asset('reported_hospital_capacity_admissions_facility_level_weekly_average_timeseries', 'anag-cw7u'),
        Asset('reported_hospital_capacity_admissions_facility_level_weekly_average_timeseries_raw', 'uqq2-txqb'),
    ]
    download_datasets(args, 'healthdata.gov', datasets)

def cdc_download(args):
    '''Download datasets hosted at data.cdc.gov endpoints'''
    datasets = [
        Asset('covid_vaccinations_state', 'unsk-b7fc'),
        Asset('covid_vaccinations_county', '8xkx-amqh'),
        Asset('covid_vaccine_allocations_state_pfizer', 'saz5-9hgg'),
        Asset('covid_vaccine_allocations_state_moderna', 'b7pe-5nws'),
        Asset('covid_vaccine_allocations_state_janssen', 'w9zu-fywh'),
        Asset('nationwide_commercial_laborator_seroprevalence_survey', 'd2tw-32xv'),
        Asset('nationwide_blood_donor_seroprevalence', 'wi5c-cscz'),
        Asset('rates_of_covid_19_cases_or_deaths_by_age_group_and_vaccination_status', '3rge-nu2a'),
        Asset('rates_of_covid_19_cases_or_deaths_by_age_group_and_vaccination_status_and_booster_dose', 'd6p8-wqjm'),
        Asset('rates_of_covid_19_cases_or_deaths_by_age_group_and_vaccination_status_and_second_booster_dose', 'ukww-au2k'),
        Asset('united_states_covid_19_community_levels_by_county', '3nnm-4jni')
    ]
    download_datasets(args, 'data.cdc.gov', datasets)


def download_datasets(args, server, datasets):
    with Socrata(server, get_socrata_app_token(args), timeout=60) as client:
        for dataset in datasets:
            logging.info('Fetching %s...', dataset.name)
            csv_file = dataset.get_csv(client)

            logging.info('Dowloaded %s. Converting to Parquet...', csv_file)
            basename, extension = os.path.splitext(csv_file)
            parquet_file = basename + '.parquet'
            csv2parquet.main_with_args(csv2parquet.convert, [
                '--codec', 'gzip',
                '--row-group-size', '10000000',
                '--output', parquet_file,
                csv_file
            ])

            logging.info('Generated Parquet. Compressing %s...', csv_file)
            subprocess.run(['bzip2', '-f', '-9', csv_file])
            s3_sync_dir = pathlib.Path(args.s3_sync_dir)
            s3_sync_dir.mkdir(exist_ok=True)
            hhs_sync_dir = pathlib.Path(f'{s3_sync_dir}/HHS')
            hhs_sync_dir.mkdir(exist_ok=True)

            logging.info('Copying files to target...')
            dataset_dir = pathlib.Path(f'{hhs_sync_dir}/{dataset.name}/v2')
            dataset_dir.mkdir(exist_ok=True, parents=True)
            csv_dir = pathlib.Path(f'{dataset_dir}/csv')
            csv_dir.mkdir(exist_ok=True)
            parquet_dir = pathlib.Path(f'{dataset_dir}/parquet')
            parquet_dir.mkdir(exist_ok=True)
            shutil.move(f'{csv_file}.bz2', f'{csv_dir}/{csv_file}.bz2')
            shutil.move(parquet_file, f'{parquet_dir}/{parquet_file}')

        logging.info('All done!')


class Asset():
    """A dataset in a Socrata server, and methods to work with it"""
    def __init__(self, name, id):
        self.name = name
        self.id = id

    def get_metadata(self, client):
        return client.get_metadata(self.id)

    def get_csv(self, client):
        metadata = self.get_metadata(client)
        updated_at = datetime.datetime.utcfromtimestamp(metadata['rowsUpdatedAt'])
        url = f'https://{client.domain}/api/views/{self.id}/rows.csv?accessType=DOWNLOAD'

        # CODE SMELL: Is the `session` attribute in the client morally private?
        r = client.session.get(url)

        outpath = f'{self.name}_{updated_at.strftime("%Y%m%d_%H%M")}.csv'
        with open(outpath, 'wb') as fd:
            for chunk in r.iter_content(chunk_size=128):
                fd.write(chunk)
        return outpath


