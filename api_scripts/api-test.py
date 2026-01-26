secrets = __import__('secrets')

from asnake.client import ASnakeClient

client = ASnakeClient(baseurl = secrets.baseurl,
                      username = secrets.username,
                      password = secrets.password)

client.authorize()

#To get a single object:
print(client.get('/repositories/2/archival_objects/74627').json()['title'])

print('------------------------')

#To get all objects:
n=0
for obj in client.get_paged('/repositories/2/digital_objects'):
    print(obj['title'])
    n += 1
    if n>10:
        break

#Top collection
print(client.get('/repositories/2/top_containers/7828').json())
