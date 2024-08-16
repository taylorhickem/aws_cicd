import os
import source_code
import cloudformation as cfn

TMP_DIR = '/tmp'
CF_DIR = 'cloudformation'
LAMBDA_SUBDIR = 'lambda_functions'
S3_DIR = ''
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
    'ACTION_TYPE',
    'STACK_NAME',
    'PRINT_UPDATES'
]
ARCHITECTURES = [
    'x86_64'
]
STATUS_TYPE = 1
S3_BUCKET = ''
STACK_NAME = ''
STACK_DIR = ''
PRINT_UPDATES = True
DEPLOY_PREFIX = 'deploy_package'
ACTION_TYPE = ['stack_update']


def lambda_handler(event, context):
    global STATUS_TYPE, STACK_DIR
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

    if STACK_NAME:
        response_body['request']['STACK_NAME'] = STACK_NAME
        STACK_DIR = os.path.join(os.path.join(TMP_DIR, CF_DIR), STACK_NAME)
        remote_dir = f'{S3_DIR}/{CF_DIR}/{STACK_NAME}'
        if PRINT_UPDATES:
            print(f'downloading source code for {STACK_NAME} from S3 bucket {S3_BUCKET} and prefix {remote_dir} ...')
        source_code.stack_download_from_s3(STACK_NAME, S3_BUCKET, s3_dir=S3_DIR, local_dir=STACK_DIR)
        if ACTION_TYPE == 'stack_update':
            message, STATUS_TYPE = stack_update(STACK_NAME, dir=STACK_DIR, print_updates=PRINT_UPDATES)
        else:
            STATUS_TYPE = 0
            message = f'INPUT ERROR. unrecognized ACTION_TYPE {ACTION_TYPE}. expected: stack_update'
    else:
        STATUS_TYPE = 0
        message = 'INPUT ERROR. No CloudFormation STACK_NAME passed.'

    response_body['Status'] = STATUS_LABELS[STATUS_TYPE]
    response_body['message'] = message
    print(f'lambda execution completed. results {response_body}')
    return response_body


def stack_update(stack_name, dir='', print_updates=True):
    if print_updates:
        print(f'pre stack update action: read config instructions from {dir} ...')
    cfn.read_stack_config(stack_name, local_dir=dir, print_updates=print_updates)
    functions_config = cfn.STACK_CONFIG.get('lambda_functions', {})
    if functions_config:
        function_names = [c['function_name'] for c in functions_config]
        if print_updates:
            print(f'pre stack update action: zip source code to S3 for lambda functions {function_names} ...')
        functions_subdir = os.path.join(dir, LAMBDA_SUBDIR)
        deploy_prefix = f'{DEPLOY_PREFIX}/lambda'
        lambda_source_code_zip(function_names, functions_subdir, 
                               S3_BUCKET, deploy_prefix=deploy_prefix, print_updates=print_updates)
    if print_updates:
        print(f'updating stack {stack_name} ...')
    message, status_type = cfn.stack_update(stack_name, print_updates=print_updates)
    return message, status_type


def lambda_source_code_zip(function_names, functions_dir, 
        s3_bucket, deploy_prefix='', print_updates=True):    
    for f in function_names:
        f_dir_name = f.replace('-','_')
        function_dir = os.path.join(functions_dir, f_dir_name)
        source_code.lambda_function_zip_to_S3(f, function_dir, 
            s3_bucket, s3_prefix=deploy_prefix, print_updates=print_updates)