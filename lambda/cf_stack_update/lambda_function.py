import os
import time
import json
from services import client_load, client_unload, clients
from layers import LayerManager
import source_code
import cloudformation as cfn

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
ARCHITECTURES = [
    'x86_64'
]
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
        if 'stack_update' in ACTION_TYPES:
            message, STATUS_TYPE = stack_update(FUNCTION_NAME)
        else:
            message = ''
            if 'layers_update' in ACTION_TYPES:
                message, STATUS_TYPE = layers_update(FUNCTION_NAME)
            if 'function_update' in ACTION_TYPES:
                # bucket_context = read_bucket_context(event) used together with S3 trigger on bucket
                # function_name = bucket_context['function_name']
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
            if all([a not in ACTION_TYPES for a in ['layers_update', 'function_update']]):
                STATUS_TYPE = 0
                message = f'USER INPUT ERROR. Unrecognized ACTION_TYPES {ACTION_TYPES}. Allowed = [function_update, stack_update, layers_update]'
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
        Architectures=ARCHITECTURES
    )
    client_unload('lambda')
    return response


def stack_update(function_name):
    print(f'pre stack update actions 1 of 2: read config instructions from {FUNCTION_DIR} ...')
    cfn.read_stack_config(function_name, local_dir=FUNCTION_DIR)
    print(f'pre stack update actions 2 of 2: zip source code to S3 for lambda function {function_name} ...')
    deploy_prefix = f'{DEPLOY_PREFIX}/lambda'
    source_code.zip_to_S3(function_name, FUNCTION_DIR, S3_BUCKET, s3_prefix=deploy_prefix)
    print(f'updating stack for lambda function {function_name} ...')
    message, status_type = cfn.stack_update(function_name)
    return message, status_type


def layers_update(function_name):
    print(f'reading Layers config for lambda function {function_name} ...')
    config_subdir = os.path.join(FUNCTION_DIR, CONFIG_DIR)
    layer_manager = LayerManager(config_subdir)
    print(f'layers: {layer_manager.layers}')
    print(f'updating {function_name} Layer Arns ...')
    message, status_type = layer_manager.lambda_layers_update(function_name)
    print(message)
    return message, status_type

# def read_bucket_context(event):
#    bucket_context = {}
#    if 'Records' in event:
#        if 's3' in event['Records'][0]:
#            object_details = event['Records'][0]['s3']['object']
#            file_path = object_details['key']
#            bucket_context['function_name'] = file_path.split('/')[1]
#    return bucket_context
