secrets = __import__('secrets')

import json, argparse
from asnake.client import ASnakeClient

client = ASnakeClient(baseurl = secrets.baseurl,
                      username = secrets.username,
                      password = secrets.password)

client.authorize()

# Initialize parser
parser = argparse.ArgumentParser()
parser.add_argument('-o', '--object_type', default='')
parser.add_argument('-i', '--identifier', default='0')
parser.add_argument('-r', '--resolve_linked_instances', default='0')

proceed = True

# Read arguments from command line
args = parser.parse_args()
object_type = args.object_type
try:
    identifier = int(args.identifier)
except:
    identifier = 0
try:
    resolve_linked_instances = int(args.resolve_linked_instances)
except:
    resolve_linked_instances = -1

if object_type not in ['digital', 'archival', 'resource']:
    print('Invalid or missing object type. Must be "digital", "archival", or "resource".')
    proceed = False

if identifier == 0:
    print('Invalid or missing identifier. Must be an integer.')
    proceed = False

if resolve_linked_instances not in [0, 1]:
    print('Invalid or missing resolve_linked_instances. Must be 0 (false, default) or 1 (true).')
    proceed = False

if proceed:

    if object_type == 'digital':
        uri = f'/repositories/2/digital_objects/'
    elif object_type == 'archival': 
        uri = f'/repositories/2/archival_objects/'
    elif object_type == 'resource':
        uri = f'/repositories/2/resources/'
    
    params = '?resolve[]=linked_instances' if resolve_linked_instances else ''
    
    obj = client.get(f'{uri}{identifier}{params}').json()    
    print(json.dumps(obj, indent=4, sort_keys=True))

'''

uri = '/repositories/2/digital_objects/8889'
uri = '/repositories/2/digital_objects/27551'
uri = '/repositories/2/archival_objects/74627'
uri = '/repositories/2/resources/219'
'''