"""updates lambda source code or layer update
"""

import os
import time
from services import client_load, client_unload, clients
from layers import LayerManager
import source_code

TMP_DIR = '/tmp'
S3_DIR = 'lambda'
CONFIG_DIR = 'config'
UPDATE_DELAY_SEC = 5
STATUS_LABELS = [
    'FAILED',
    'SUCCESS'
]
ENV_VARIABLES = [
    'S3_BUCKET'
]
EVENT_VARIABLES = [
    'ACTION_TYPES',
    'FUNCTION_NAME'
]
FUNCITON_ARCHITECTURE = 'x86_64'
STATUS_TYPE = 1
S3_BUCKET = ''
FUNCTION_NAME = ''
FUNCTION_DIR = ''
DEPLOY_PREFIX = 'deploy_package'
ACTION_TYPES = ['function_update']


def lambda_handler(event, context):
    global STATUS_TYPE, FUNCTION_DIR
    STATUS_TYPE = 1
    response_body = {
        'statusCode': 200,
        'Status': STATUS_LABELS[STATUS_TYPE],
        'message': ''
    }
    response_body['request'] = {}
    response_body['environment'] = {}

    for v in ENV_VARIABLES:
        globals()[v] = os.environ[v]
        response_body['environment'][v] = os.environ[v]

    for a in event:
        if a in EVENT_VARIABLES:
            globals()[a] = event[a]
            response_body['request'][a] = event[a]

    if FUNCTION_NAME:
        response_body['request']['FUNCTION_NAME'] = FUNCTION_NAME
        FUNCTION_DIR = os.path.join(TMP_DIR, FUNCTION_NAME)
        remote_dir = f'{S3_DIR}/{FUNCTION_NAME}'
        print(f'downloading source code for {FUNCTION_NAME} from S3 bucket {S3_BUCKET} and prefix {remote_dir} ...')
        source_code.download_from_s3(FUNCTION_NAME, S3_BUCKET, s3_dir=S3_DIR, local_dir=FUNCTION_DIR)
        message = ''
        if 'layers_update' in ACTION_TYPES:
            message, STATUS_TYPE = layers_update(FUNCTION_NAME)
        if 'function_update' in ACTION_TYPES:
            if STATUS_TYPE == 1 and 'layers_update' in ACTION_TYPES:
                print(f'pausing for {UPDATE_DELAY_SEC} sec to free up AWS lambda deploy resources ...')
                time.sleep(UPDATE_DELAY_SEC)
            try:
                response_body['lambda_response'] = function_update(FUNCTION_NAME)
                STATUS_TYPE = 1 * STATUS_TYPE
                message = message + ' ' + f'lambda function update: SUCCESS. updated code for {FUNCTION_NAME}.'
            except Exception as e:
                STATUS_TYPE = 0
                message = message + ' ' + f'lambda function update: ERROR. failed to update lambda funciton code {FUNCTION_NAME}. {str(e)}'
        if all([a not in ['layers_update', 'function_update'] for a in ACTION_TYPES]):
            STATUS_TYPE = 0
            message = f'USER INPUT ERROR. Unrecognized ACTION_TYPES: {ACTION_TYPES}. Allowed = [function_update, layers_update]'
    else:
        STATUS_TYPE = 0
        message = 'USER INPUT ERROR. No Lambda FUNCTION_NAME passed.'

    response_body['Status'] = STATUS_LABELS[STATUS_TYPE]
    response_body['message'] = message
    print(f'lambda execution completed. results {response_body}')
    return response_body


def function_update(function_name):
    zipobj = source_code.zip_buffer(FUNCTION_DIR)
    source_code_bytes = zipobj.getvalue()

    client_load('lambda')
    response = clients['lambda'].update_function_code(
        FunctionName=function_name,
        ZipFile=source_code_bytes,
        Architectures=[FUNCITON_ARCHITECTURE]
    )
    client_unload('lambda')
    return response


def layers_update(function_name):
    print(f'reading Layers config for lambda function {function_name} ...')
    config_subdir = os.path.join(FUNCTION_DIR, CONFIG_DIR)
    layer_manager = LayerManager(config_subdir)
    print(f'layers: {layer_manager.layers}')
    print(f'updating {function_name} Layer Arns ...')
    message, status_type = layer_manager.lambda_layers_update(function_name)
    print(message)
    return message, status_type