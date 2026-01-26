import csv
import json

from asnake.client import ASnakeClient

secrets = __import__('secrets')

client = ASnakeClient(baseurl = secrets.baseurl,
                      username = secrets.username,
                      password = secrets.password)

client.authorize()

resource_id = "228"

resource_tree = client.get(f"/repositories/2/resources/{resource_id}/ordered_records").json()
print(json.dumps(resource_tree, indent=4, sort_keys=True))

'''
with open(f"/tmp/items.csv", mode="w") as csv_file:
    fieldnames = ['TITLE', 'URI', 'PARENT', 'COMPONENT_ID']
    csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    csv_writer.writeheader()

    for tree_item in resource_tree["uris"]:
        if tree_item["level"] == "file":
            archival_object = asnake_client.get(f'{tree_item["ref"]}?resolve[]=parent').json()
            row = {}
            row['TITLE'] = archival_object['title']
            row['URI'] = archival_object['uri']
            row['PARENT'] = archival_object['parent']['_resolved']['title']
            # NOTE HistoricalFiles_? will fail
            row['COMPONENT_ID'] = archival_object['component_id']

            print(json.dumps(row, indent=4), flush=True)
            csv_writer.writerow(row)
'''

