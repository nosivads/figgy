secrets = __import__('secrets')

from asnake.client import ASnakeClient

client = ASnakeClient(baseurl = secrets.baseurl,
                      username = secrets.username,
                      password = secrets.password)

client.authorize()

colls=dict()

not_found = 0

loop = True
for obj in client.get_paged('repositories/2/digital_objects'):
    # select published objects only
    if obj['publish'] and not obj['suppressed']:
        incl=False
        for file_version in obj['file_versions']:
            if file_version['publish']:
                if file_version['file_uri'][:4]=='http':
                    incl=True
        # select published and http references only
        if incl:
            # iterate over collection references (usually only one)
            for collectionid in obj['collection']:
                # filter out accession records
                if collectionid['ref'][16:26] != 'accessions':
                    # use object reference as key
                    if collectionid['ref'] in colls.keys():
                        # if the collection is already in colls, increment
                        colls[collectionid['ref']] = colls[collectionid['ref']] + 1
                    else:
                        # otherwise add reference to collectionn
                        colls[collectionid['ref']] = 1

                    for v in obj['file_versions']:
                        if v['publish']:
                            try:
                                print(v['link_uri'])
                            except:
                                continue
                            try:
                                print(v['file_uri'])
                            except:
                                print('link not foundd')
                                not_found += 1

colls = dict(sorted(colls.items(), key=lambda item: item[1], reverse=True))

for coll in colls:
    if client.get(coll).json()['publish'] and not client.get(coll).json()['suppressed']:
        print(client.get(coll).json()['title'], colls[coll])
    docount=sum(colls.values())

print('DO count:', docount)
print('not found count:', not_found)
