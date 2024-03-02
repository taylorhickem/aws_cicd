import os
import time
import json
import re
from services import client_load, client_unload, clients
from layers import LayerManager

TMP_DIR = '/tmp'
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
STACK_CONFIG = {
    'StackName': '',
    'template': '',
    'tags': {},
    'layers': {},
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


def stack_update(function_name):
    status_type = 1
    message = ''
    stack_name = STACK_CONFIG['StackName']
    print(f'INFO. stack name: {stack_name} for lambda function {function_name}.')
    client_load('cloudformation')
    stack_status = get_stack_status(stack_name)
    if stack_status in [STACK_ALIVE_STATUS, STACK_ROLLBACK_STATUS]:
        print(f'{stack_name} stack already exists. deleting stack ...')
        try:
            message, status_type = stack_rollback(stack_name)
        except Exception as e:
            status_type = 0
            message = f'ERROR. {stack_name} stack delete failed. {str(e)}'
    stack_status = get_stack_status(stack_name)
    if stack_status == STACK_DELETED_STATUS:
        print(f'{stack_name} stack does not exists. deploying stack ...')
        try:
            message, status_type = stack_deploy(stack_name)
        except Exception as e:
            status_type = 0
            message = f'ERROR. {stack_name} stack deploy failed. {str(e)}'
    else:
        status_type = 0
        message = f'ERROR. {stack_name} stack deploy aborted. stack status: {stack_status}'

    client_unload('cloudformation')
    return message, status_type


def read_stack_config(function_name, local_dir=''):
    global STACK_CONFIG
    sn_label = 'StackName'
    if not local_dir:
        local_dir = os.path.join(TMP_DIR, function_name)
    config_subdir = os.path.join(local_dir, CONFIG_DIR)
    STACK_CONFIG['template'] = read_stack_template_yaml(local_dir)
    STACK_CONFIG['tags'] = read_stack_tags(config_subdir)
    layers = read_stack_layers(config_subdir)
    STACK_CONFIG['layers'] = layers
    parameters = read_stack_parameters(config_subdir, layers=layers)
    STACK_CONFIG['parameters'] = parameters
    STACK_CONFIG['rollback_actions'] = read_stack_rollback_actions(config_subdir, params=parameters)
    parameters = STACK_CONFIG['parameters']
    if parameters:
        STACK_CONFIG[sn_label] = parameters[sn_label]


def read_stack_template_yaml(local_dir) -> str:
    template_yaml = ''
    root_files = os.listdir(local_dir)
    print(f'cfn root dir found with files {root_files}')
    if CFN_TEMPLATE_FILE in root_files:
        file_path = os.path.join(local_dir, CFN_TEMPLATE_FILE)
        with open(file_path, 'r') as f:
            template_yaml = f.read()

    return template_yaml


def read_stack_tags(local_dir) -> dict:
    tags = {}
    if os.path.exists(local_dir):
        config_files = os.listdir(local_dir)
        if CFN_TAGS_FILE in config_files:
            file_path = os.path.join(local_dir, CFN_TAGS_FILE)
            with open(file_path, 'r') as f:
                tags = json.load(f)
                f.close()
                print(f'cfn tags {tags}')
    return tags


def read_stack_layers(local_dir) -> dict:
    layers = {}
    if os.path.exists(local_dir):
        print('checking for layer config ...')
        layer_manager = LayerManager(local_dir)
        if layer_manager.has_layers():
            layers = layer_manager.layers
            print(f'cfn layers {layers}')
    return layers


def read_stack_parameters(local_dir, layers={}) -> dict:
    parameters = {}
    print(f'cfn config directory {local_dir}')
    if os.path.exists(local_dir):
        config_files = os.listdir(local_dir)
        print(f'cfn config dir found with files {config_files}')
        if CFN_PARAMETERS_FILE in config_files:
            file_path = os.path.join(local_dir, CFN_PARAMETERS_FILE)
            with open(file_path, 'r') as f:
                parameters = json.load(f)
                print(f'cfn config parameters {parameters}')
                f.close()
    print('updating stack parameters with aws account parameters ...')
    aws_parameters_update(parameters)
    if layers:
        print('updating stack parameters with layer Arns ...')
        layer_arn_parameters_update(parameters, layers)
    elif 'LayerArns' in parameters:
        del parameters['LayerArns']

    return parameters


def read_stack_rollback_actions(local_dir, params={}) -> dict:
    rollback_actions = {}
    if os.path.exists(local_dir):
        config_files = os.listdir(local_dir)
        print(f'cfn config dir found with files {config_files}')
        if CFN_ROLLBACK_FILE in config_files:
            file_path = os.path.join(local_dir, CFN_ROLLBACK_FILE)
            with open(file_path, 'r') as f:
                ra_source = f.read()
                f.close()
            ra_str = parameters_substitute(ra_source, params)
            rollback_actions = json.loads(ra_str)
            print(f'cfn rollback file {rollback_actions}')

    return rollback_actions


def stack_deploy(stack_name):
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
        # print(f'stack template: \n {template_yaml}')
        print(f'deploying cloudformation stack {stack_name} from template with parameters {params} and tags {tags} ...')
        cfn_response = clients['cloudformation'].create_stack(**create_args)
        while stack_status not in [STACK_ROLLBACK_STATUS, STACK_ALIVE_STATUS]:
            time.sleep(STACK_POLL_SEC)
            stack_status = get_stack_status(stack_name)
            print(f'{stack_name} stack status: {stack_status}')

    if stack_status == STACK_ALIVE_STATUS:
        message = f'SUCCESS. {stack_name} stack deploy complete.'
        print(message)
    elif stack_status == STACK_ROLLBACK_STATUS:
        status_type = 0
        message = f'FAILED. {stack_name} deploy unsuccessful error encountered and stack rolled back. {cfn_response}'
        print(message)
    else:
        status_type = 0
        fail_message = f'{stack_name} deploy failed. stack status: {stack_status}. {cfn_response}'
        message = fail_message + message
        print(fail_message)
    client_unload('cloudformation')
    return message, status_type


def stack_rollback(stack_name):
    status_type = 1
    message = f'PENDING. {stack_name} stack rollback initiated ...'
    client_load('cloudformation')
    stack_status = get_stack_status(stack_name)
    if not stack_status == STACK_DELETED_STATUS:
        message, status_code = stack_pre_rollback_run(stack_name)
        if status_code == 200:
            print(f'{stack_name} pre-rollback actions complete. rolling back stack ...')
            response = clients['cloudformation'].delete_stack(StackName=stack_name)
            while not stack_status == STACK_DELETED_STATUS:
                time.sleep(STACK_POLL_SEC)
                stack_status = get_stack_status(stack_name)
                print(f'{stack_name} stack status: {stack_status}')
        else:
            status_type = 0
            message = f'{stack_name} pre rollback actions failed. {message}'
            print(message)

    if stack_status == STACK_DELETED_STATUS:
        message = f'SUCCESS. {stack_name} stack delete complete.'
        print(message)
    else:
        status_type = 0
        fail_message = f'{stack_name} stack delete failed. stack status {stack_status}'
        message = fail_message + message
        print(fail_message)
    client_unload('cloudformation')
    return message, status_type


def stack_pre_rollback_run(stack_name):
    def action_run(action_spec):
        status_code = 200
        message = f'{stack_name} pre-rollback action success.'
        service = action_spec['resource_type']
        print(f'searching pre-rollback instructions ...')
        if service in ROLLBACK_ACTIONS['services']:
            if service == 'lambda':
                service_action = ROLLBACK_ACTIONS['services'][service][0]
                if service_action == 'invoke':
                    lambda_function = action_spec['resource_name']
                    request_body = json.dumps(action_spec['request_body'])
                    print(f'executing pre-rollback using lambda: {lambda_function} and request {request_body}')
                    client_load('lambda')
                    lambda_response = clients['lambda'].invoke(
                        FunctionName=lambda_function,
                        Payload=request_body
                    )
                    client_unload('lambda')
                    status_code = lambda_response['StatusCode']
                    if status_code != 200:
                        error_details = lambda_response['FunctionError'] if 'FunctionError' in lambda_response else ''
                        message = f'ERROR. {stack_name} pre-rollback action failed. {error_details}'
                    else:
                        print(message)

        return message, status_code

    print(f'running pre-rollback back actions for stack {stack_name} ...')
    rollback_actions = STACK_CONFIG['rollback_actions']
    for a in rollback_actions:
        message, status_code = action_run(a)
    return message, status_code


def stack_exists(stack_name):
    stack_status = get_stack_status(stack_name)
    stack_alive = stack_status == STACK_ALIVE_STATUS
    return stack_alive


def stack_is_dead(stack_name):
    stack_status = get_stack_status(stack_name)
    stack_dead = stack_status in [STACK_DELETED_STATUS, STACK_ROLLBACK_STATUS]
    return stack_dead


def get_stack_status(stack_name):
    stack_status = STACK_DELETED_STATUS
    try:
        stacks = clients['cloudformation'].describe_stacks(StackName=stack_name)['Stacks']
        print(f'describe_stacks response {stacks}')
        if len(stacks) > 0:
            stack_details = [s for s in stacks if s['StackName'] == stack_name][0]
            stack_status = stack_details['StackStatus']
    except:
        pass
    return stack_status


def aws_parameters_update(params):
    params['AccountId'] = get_account_id()


def layer_arn_parameters_update(params, layers):
    params['LayerArns'] = ','.join([l['Arn'] for l in layers])


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
