import os
import time
import json
import re
from services import client_load, client_unload, clients
from layers import LayerManager
from source_code import read_file


TMP_DIR = '/tmp'
CFN_DIR = 'cloudformation'
CONFIG_DIR = 'config'
STACK_ALIVE_STATUS = 'CREATE_COMPLETE'
STACK_ROLLBACK_STATUS = 'ROLLBACK_COMPLETE'
STACK_DELETED_STATUS = 'DELETE_COMPLETE'
STACK_POLL_SEC = 10
PARAM_DELIM = '%'
CFN_PARAMETERS_FILE = 'cfn_parameters.json'
CFN_TEMPLATE_FILE = 'cfn_template.yaml'
CFN_ROLLBACK_FILE = 'cfn_pre_rollback_actions.json'
CFN_TAGS_FILE = 'cfn_tags.json'
CFN_LAMBDA_FUNCTIONS_FILE = 'cfn_lambda_functions.json'
LAMBDA_SUBDIR = 'lambda_functions'
LAYER_ARNS_TAG = 'LayerArns'
LAMBDA_FUNCTION_TAG = 'FunctionName'
STACK_CONFIG = {
    'StackName': '',
    'template': '',
    'tags': {},
    'lambda_functions': [],
    'parameters': {},
    'rollback_actions': {}
}
ROLLBACK_ACTIONS = {
    'services': {
        'lambda': [
            'invoke'
        ]
    }
}


def stack_update(stack_name, print_updates=True):
    status_type = 1
    message = ''
    if print_updates:
        print(f'INFO. stack name: {stack_name}.')
    client_load('cloudformation')
    stack_status = get_stack_status(stack_name, print_updates=print_updates)
    if stack_status in [STACK_ALIVE_STATUS, STACK_ROLLBACK_STATUS]:
        if print_updates:
            print(f'{stack_name} stack already exists. deleting stack ...')
        try:
            message, status_type = stack_rollback(stack_name, print_updates=print_updates)
        except Exception as e:
            status_type = 0
            message = f'ERROR. {stack_name} stack delete failed. {str(e)}'
    stack_status = get_stack_status(stack_name, print_updates=print_updates)
    if stack_status == STACK_DELETED_STATUS:
        if print_updates:
            print(f'{stack_name} stack does not exists. deploying stack ...')
        try:
            message, status_type = stack_deploy(stack_name, print_updates=print_updates)
        except Exception as e:
            status_type = 0
            message = f'ERROR. {stack_name} stack deploy failed. {str(e)}'
    else:
        status_type = 0
        message = f'ERROR. {stack_name} stack deploy aborted. stack status: {stack_status}'

    client_unload('cloudformation')
    return message, status_type


def read_stack_config(stack_name, local_dir='', print_updates=False):
    global STACK_CONFIG
    sn_label = 'StackName'
    if not local_dir:
        local_dir = os.path.join(os.path.join(TMP_DIR, CFN_DIR), stack_name)
    config_subdir = os.path.join(local_dir, CONFIG_DIR)
    STACK_CONFIG['template'] = read_file(CFN_TEMPLATE_FILE, file_type='text',
       dir=local_dir, default='', print_updates=print_updates)
    STACK_CONFIG['tags'] = read_file(CFN_TAGS_FILE, file_type='json',
        dir=config_subdir, default={}, print_updates=print_updates)
    lambda_functions = read_lambda_functions(
        local_dir=local_dir, config_dir=config_subdir, print_updates=print_updates)
    if lambda_functions:
        STACK_CONFIG['lambda_functions'] = lambda_functions
    parameters = read_stack_parameters(config_subdir, lambda_functions=lambda_functions, print_updates=print_updates)
    if parameters:
        if sn_label in parameters:
            STACK_CONFIG[sn_label] = parameters[sn_label]
        STACK_CONFIG['parameters'] = parameters
        STACK_CONFIG['rollback_actions'] = read_stack_rollback_actions(config_subdir, params=parameters)


def read_lambda_functions(local_dir='', config_dir='', print_updates=False) -> dict:
    lambda_functions = []
    function_tags = read_file(CFN_LAMBDA_FUNCTIONS_FILE, file_type='json',
        dir=config_dir, default={}, print_updates=print_updates)
    if function_tags:
        for t, f in function_tags.items():
            f_dir_name = f.replace('-', '_')
            function_config_dir = os.path.join(
                os.path.join(
                    os.path.join(local_dir, LAMBDA_SUBDIR), 
                    f_dir_name), CONFIG_DIR)
            layers = read_lambda_layers(function_config_dir, print_updates=print_updates)
            lambda_function = {
                'param_name': t,
                'function_name': f,
                'layers': layers
            }
            if print_updates:
                print(f'found lambda function config {lambda_function}')
            lambda_functions.append(lambda_function)
    return lambda_functions


def read_lambda_layers(function_config_dir='', print_updates=False) -> dict:
    layers = {}
    if os.path.exists(function_config_dir):
        if print_updates:
            print('checking for layer config ...')
        layer_manager = LayerManager(function_config_dir)
        if layer_manager.has_layers():
            layers = layer_manager.layers
            if print_updates:
                print(f'cfn layers {layers}')
    return layers


def read_stack_parameters(local_dir, lambda_functions=[], print_updates=False) -> dict:
    parameters = read_file(
        CFN_PARAMETERS_FILE,
        file_type='json', 
        dir=local_dir,
        default={}, 
        print_updates=print_updates
    )
    if parameters:
        print('updating stack parameters with aws account parameters ...')
        aws_parameters_update(parameters)
        if lambda_functions:
            print('updating stack parameters with Lambda function names and layer Arns ...')
            stack_params_update_lambda_functions(parameters, lambda_functions=lambda_functions)        
    return parameters


def stack_params_update_lambda_functions(params, lambda_functions=[]):
    for f in lambda_functions:
        param_name = f['param_name']
        function_name = f['function_name']
        layers = f.get('layers', {})
        function_name_key = f'{param_name}{LAMBDA_FUNCTION_TAG}'
        params.update({function_name_key: function_name})
        if layers:
            layer_arns_key = f'{param_name}{LAYER_ARNS_TAG}'
            layer_arn_parameters_update(params, layer_arns_key, layers)


def read_stack_rollback_actions(local_dir, params={}, print_updates=False) -> dict:
    ra_source = read_file(
        CFN_ROLLBACK_FILE,
        file_type='text',
        dir=local_dir,
        default='',
        print_updates=print_updates
    )
    ra_str = parameters_substitute(ra_source, params)
    rollback_actions = json.loads(ra_str)
    if print_updates:
        print(f'cfn rollback file {rollback_actions}')
    return rollback_actions


def stack_deploy(stack_name, print_updates=True):
    def get_stack_create_args(stack_name, template_yaml, params={}, tags={}):
        create_args = {
            'StackName': stack_name,
            'TemplateBody': template_yaml
        }
        if params:
            stack_params = [
                {'ParameterKey': p,
                 'ParameterValue': params[p]
                 } for p in params if p not in ['StackName']
            ]
            create_args['Parameters'] = stack_params
        if tags:
            stack_tags = [
                {'Key': t,
                 'Value': tags[t]
                 } for t in tags
            ]
            create_args['Tags'] = stack_tags
        return create_args

    status_type = 1
    cfn_response = {}
    message = f'PENDING. {stack_name} stack deploy initiated ...'
    client_load('cloudformation')
    stack_status = get_stack_status(stack_name)
    if stack_status == STACK_ALIVE_STATUS:        
        message = f'SUCCESS. {stack_name} stack already deployed and ready.'
    elif stack_status == STACK_ROLLBACK_STATUS:
        message = f'SUCCESS. {stack_name} stack already exists. delete stack and re-deloy.'
    else:
        template_yaml = STACK_CONFIG['template']
        params = STACK_CONFIG['parameters']
        tags = STACK_CONFIG['tags']
        create_args = get_stack_create_args(
            stack_name,
            template_yaml,
            params=params,
            tags=tags
        )
        create_args['Capabilities'] = ['CAPABILITY_IAM', 'CAPABILITY_AUTO_EXPAND']
        if print_updates:
            print(f'deploying cloudformation stack {stack_name} from template with parameters {params} and tags {tags} ...')
        cfn_response = clients['cloudformation'].create_stack(**create_args)
        while stack_status not in [STACK_ROLLBACK_STATUS, STACK_ALIVE_STATUS]:
            time.sleep(STACK_POLL_SEC)
            stack_status = get_stack_status(stack_name)
            if print_updates:
                print(f'{stack_name} stack status: {stack_status}')

    if stack_status == STACK_ALIVE_STATUS:
        message = f'SUCCESS. {stack_name} stack deploy complete.'
        if print_updates:
            print(message)
    elif stack_status == STACK_ROLLBACK_STATUS:
        status_type = 0
        message = f'FAILED. {stack_name} deploy unsuccessful error encountered and stack rolled back. {cfn_response}'
        if print_updates:
            print(message)
    else:
        status_type = 0
        fail_message = f'{stack_name} deploy failed. stack status: {stack_status}. {cfn_response}'
        message = fail_message + message
        if print_updates:
            print(fail_message)
    client_unload('cloudformation')
    return message, status_type


def stack_rollback(stack_name, print_updates=True):
    status_type = 1
    message = f'PENDING. {stack_name} stack rollback initiated ...'
    client_load('cloudformation')
    stack_status = get_stack_status(stack_name)
    if not stack_status == STACK_DELETED_STATUS:
        message, status_code = stack_pre_rollback_run(stack_name)
        if status_code // 100 == 2:
            if print_updates:
                print(f'{stack_name} pre-rollback actions complete. rolling back stack ...')
            response = clients['cloudformation'].delete_stack(StackName=stack_name)
            while not stack_status == STACK_DELETED_STATUS:
                time.sleep(STACK_POLL_SEC)
                stack_status = get_stack_status(stack_name)
                print(f'{stack_name} stack status: {stack_status}')
        else:
            status_type = 0
            message = f'{stack_name} pre rollback actions failed. {message}'
            if print_updates:
                print(message)

    if stack_status == STACK_DELETED_STATUS:
        message = f'SUCCESS. {stack_name} stack delete complete.'
        if print_updates:
            print(message)
    else:
        status_type = 0
        fail_message = f'{stack_name} stack delete failed. stack status {stack_status}'
        message = fail_message + message
        if print_updates:
            print(fail_message)
    client_unload('cloudformation')
    return message, status_type


def stack_pre_rollback_run(stack_name, print_updates=True):
    def action_run(action_spec):
        status_code = 200
        message = f'{stack_name} pre-rollback action success.'
        service = action_spec['resource_type']
        if print_updates:
            print(f'searching pre-rollback instructions ...')
        if service in ROLLBACK_ACTIONS['services']:
            if service == 'lambda':
                service_action = ROLLBACK_ACTIONS['services'][service][0]
                if service_action == 'invoke':
                    lambda_function = action_spec['resource_name']
                    request_body = json.dumps(action_spec['request_body'])
                    if print_updates:
                        print(f'executing pre-rollback using lambda: {lambda_function} and request {request_body}')
                    client_load('lambda')
                    try:
                        lambda_response = clients['lambda'].invoke(
                            FunctionName=lambda_function,
                            Payload=request_body
                        )
                    except Exception as e:
                        lambda_response = {
                            'StatusCode': 400,
                            'FunctionError': f'ERROR. failed to invoke lambda. {str(e)}'
                        }                        
                    client_unload('lambda')
                    if print_updates:
                        print(f'pre-rollback lambda response: {lambda_response}')
                    status_code = lambda_response['StatusCode']
                    if status_code // 100 != 2:
                        error_details = lambda_response['FunctionError'] if 'FunctionError' in lambda_response else ''
                        message = f'ERROR. {stack_name} pre-rollback action failed. {error_details}'

        return message, status_code
    if print_updates:
        print(f'running pre-rollback back actions for stack {stack_name} ...')
    rollback_actions = STACK_CONFIG['rollback_actions']
    message = ''
    status_code = 200
    for a in rollback_actions:
        action_message, action_status = action_run(a)
        if message:
            message = f'{message} \n {action_message}'
        else:
            message = action_message
        if status_code // 100 == 2:
            status_code = action_status
    return message, status_code


def stack_exists(stack_name):
    stack_status = get_stack_status(stack_name)
    stack_alive = stack_status == STACK_ALIVE_STATUS
    return stack_alive


def stack_is_dead(stack_name):
    stack_status = get_stack_status(stack_name)
    stack_dead = stack_status in [STACK_DELETED_STATUS, STACK_ROLLBACK_STATUS]
    return stack_dead


def get_stack_status(stack_name, print_updates=True):
    stack_status = STACK_DELETED_STATUS
    try:
        stacks = clients['cloudformation'].describe_stacks(StackName=stack_name)['Stacks']
        if print_updates:
            print(f'describe_stacks response {stacks}')
        if len(stacks) > 0:
            stack_details = [s for s in stacks if s['StackName'] == stack_name][0]
            stack_status = stack_details['StackStatus']
    except:
        pass
    return stack_status


def aws_parameters_update(params):
    params['AccountId'] = get_account_id()


def layer_arn_parameters_update(params, key, layers):
    params[key] = ','.join([l['Arn'] for l in layers])


def get_account_id():
    client_load('sts')
    account_id = clients['sts'].get_caller_identity()['Account']
    client_unload('sts')
    return account_id


def parameters_substitute(source_str, params) -> str:
    regex_expression = f'{PARAM_DELIM}[^]]*{PARAM_DELIM}'
    target_str = re.sub(
        regex_expression,
        lambda x: params[x.group(0).replace('params.', '').replace(PARAM_DELIM, '')],
        source_str
    )
    return target_str


