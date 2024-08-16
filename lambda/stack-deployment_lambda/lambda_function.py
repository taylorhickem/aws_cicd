import os
import json
from services import client_load, client_unload, clients


ENV_VARIABLES = [
    'STACK_LAMBDA',
    'FUNCTION_LAMBDA'
]
EVENT_VARIABLES = [
    'ACTIONS'
]
STATUS_LABELS = [
    'FAILED',
    'SUCCESS'
]
ACTIONS = []
STATUS_TYPE = 1
STACK_LAMBDA = ''
FUNCTION_LAMBDA = ''


def lambda_handler(event, context):
    global STATUS_TYPE
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

    executions = []
    if ACTIONS:
        for action in ACTIONS:
            action_message, action_status = resource_update(**action)
            execution = {
                'message': action_message,
                'status': action_status
            }
            executions.append(execution)
        STATUS_TYPE = 1 if all([e['status'] == 1 for e in executions]) else 0

    response_body['Status'] = STATUS_LABELS[STATUS_TYPE]
    response_body['executions'] = executions

    print(f'lambda execution completed. results {response_body}')
    return response_body


def resource_update(action_type='', stack_name='', function_name=''):
    message = ''
    status = 0

    if action_type == 'stack_update':
        if stack_name:
            message, status = stack_update(stack_name)
        else:
            status = 0
            message = f'ERROR. required parameter stack_name not found. '
    elif action_type == 'function_update':
        if function_name:
            message, status = function_update(function_name)
        else:
            status = 0
            message = f'ERROR. required parameter function_name not found. '
    elif action_type == 'layers_update':
        if function_name:
            message, status = layers_update(function_name)
        else:
            status = 0
            message = f'ERROR. required parameter function_name not found. '
    else:
        status = 0
        message = f'ERROR. unrecognized action_type: {action_type}'

    return message, status


def stack_update(stack_name):
    action_type = 'stack_update'
    payload_json = {
        'ACTION_TYPE': action_type,
        'STACK_NAME': stack_name
    }
    message, status = lambda_invoke(
        function_name=STACK_LAMBDA,
        action_type=action_type,
        payload_json=payload_json
    )
    return message, status
    

def function_update(function_name):
    action_type = 'function_update'
    payload_json = {
        'ACTION_TYPES': [action_type],
        'FUNCTION_NAME': function_name
    }
    message, status = lambda_invoke(
        function_name=FUNCTION_LAMBDA,
        action_type=action_type,
        payload_json=payload_json
    )
    return message, status


def layers_update(function_name):
    action_type = 'layers_update'
    payload_json = {
        'ACTION_TYPES': [action_type],
        'FUNCTION_NAME': function_name
    }
    message, status = lambda_invoke(
        function_name=FUNCTION_LAMBDA,
        action_type=action_type,
        payload_json=payload_json
    )
    return message, status


def lambda_invoke(function_name, action_type='', payload_json={}):
    message = ''
    status = 0
    payload_str = json.dumps(payload_json)
    client_load('lambda')
    response = clients['lambda'].invoke(
        FunctionName=function_name,
        InvocationType='Event',
        Payload=payload_str
    )
    client_unload('lambda')
    response_status = response.get('StatusCode', 400)
    status = 1 if response_status // 100 == 2 else 0
    if status == 1:
        message = f'SUCCESS. {action_type} for {payload_json} lambda {function_name} invoke submitted.'
    else:
        function_errors = response.get('FunctionError', '')
        data_json = {}
        data = response.get('Payload', None)
        if data:
            data_str = data.read()
            data_json = json.loads(data_str) if data_str else {}
        message = f'ERROR.  {action_type} for {payload_json} lambda {function_name} invoke failed.' + f'response: {data_json}' + f'. status: {response_status}' + f'. errors: {function_errors}'
    return message, status
