import os
import json
from services import client_load, client_unload, clients, get_bucket_region

ENV_VARIABLES = [
    'S3_BUCKET'
]
LAYERS_CONFIG_FILE = 'layers.json'
CONFIG_DIR = ''
ACCOUNT_PARAMETERS = {
    'name': 'name',
    'version': 'version',
    'account': 'AccountId',
    'region': 'region'
}


class LayerManager(object):
    layers = {}
    layers_count = 0

    def __init__(self, config_dir):
        global CONFIG_DIR
        CONFIG_DIR = config_dir
        config_files = os.listdir(CONFIG_DIR)
        if LAYERS_CONFIG_FILE in config_files:
            print('found layer config file. parsing layer information ...')
            layers_path = os.path.join(CONFIG_DIR, LAYERS_CONFIG_FILE)
            with open(layers_path, 'r') as f:
                self.layers = json.load(f)
                f.close()
            if isinstance(self.layers, list):
                self.layers_count = len(self.layers)
            self._update_account_params()
            self._update_layer_arns()

    def _update_account_params(self):
        if self.has_layers:
            account_id, region = get_account_params()
            acct_key = ACCOUNT_PARAMETERS['account']
            region_key = ACCOUNT_PARAMETERS['region']
            for i in range(self.layers_count):
                self.layers[i][acct_key] = self.layers[i][acct_key] if self.layers[i][acct_key] else account_id
                self.layers[i][region_key] = self.layers[i][region_key] if self.layers[i][region_key] else region

    def has_layers(self):
        return self.layers_count > 0

    def _update_layer_arns(self):
        if self.has_layers():
            for i in range(self.layers_count):
                name = self.layers[i][ACCOUNT_PARAMETERS['name']]
                version = self.layers[i][ACCOUNT_PARAMETERS['version']]
                region = self.layers[i][ACCOUNT_PARAMETERS['region']]
                account = self.layers[i][ACCOUNT_PARAMETERS['account']]
                arn_str = layer_arn(name, version, region, account)
                self.layers[i]['Arn'] = self.layers[i]['Arn'] if 'Arn' in self.layers[i] else arn_str

    def layer_arns(self):
        arns = []
        if self.has_layers():
            arns = [l['Arn'] for l in self.layers]
        return arns


def layer_arn(name, version, region, account):
    arn = f'arn:aws:lambda:{region}:{account}:layer:{name}:{version}'
    return arn


def get_account_params():
    client_load('sts')
    account_id = clients['sts'].get_caller_identity()['Account']
    client_unload('sts')
    bucket_name = os.environ['S3_BUCKET']
    region_name = get_bucket_region(bucket_name)
    return account_id, region_name
