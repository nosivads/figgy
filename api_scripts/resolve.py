import json

from asnake.client import ASnakeClient

secrets = __import__('secrets')

client = ASnakeClient(baseurl = secrets.baseurl,
                      username = secrets.username,
                      password = secrets.password)

client.authorize()

route = '/repositories/2/archival_objects/74627'

rec = client.get(f'{route}?resolve[]=parent&resolve[]=ancestors').json()

print(json.dumps(rec, indent=4, sort_keys=True))