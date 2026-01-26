
from pathlib import Path
from datetime import datetime
import csv

# local imports
from app.db import get_db
from util import secrets

# ArchivesSpace API authentication
from asnake.client import ASnakeClient
client = ASnakeClient(baseurl = secrets.baseurl,
                        username = secrets.username,
                        password = secrets.password)

def csv_gen(filename, fieldnames, category):

    client.authorize()

    rec_count = 0
    with open(Path(Path(__file__).resolve().parent).joinpath(filename), 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for obj in client.get_paged('/repositories/2/'+category):
            writer.writerow({fieldname: obj.get(fieldname)for fieldname in fieldnames})
            rec_count += 1

    return rec_count


# read notes from collection; returns string
def get_notes(id):

    description = ''

    client.authorize()

    uri = '/repositories/2/resources/'+id
    collection = client.get(uri)

    try:
        for note in collection.json()['notes']:
            note_type = note['type']
            note_list = list()
            if note['jsonmodel_type']=='note_multipart':
                try:
                    for subnote in note['subnotes']:
                        note_list.append(subnote['content'])
                except:
                    continue
            elif note['jsonmodel_type']=='note_singlepart':
                try:
                    for content in note['content']:
                        note_list.append(content)
                except:
                    continue
            else:
                continue

            if description == '' and note_type == 'abstract':
                description = ' '.join(note_list)
            elif description == '' and note_type == 'scopecontent':
                description = ' '.join(note_list)
    except:
        pass
            #description = description + ' (' + note_type + ') ' + ' '.join(note_list)
    return description

# return formatted last_update
def get_last_update(fn):
    db = get_db()
    query = 'SELECT dt FROM last_update WHERE fn=?;'
    last_update = db.execute(query, [fn]).fetchone()[0]
    dt = datetime.fromisoformat(last_update).strftime("%b %-d, %Y, %-I:%M%p")
    return dt

# write ISO last update; return formatted last_update (i.e. now)
def write_last_update(fn):
    db = get_db()
    query = 'UPDATE last_update SET dt=? WHERE fn=?;'
    now = datetime.now()
    last_update = now.isoformat()
    db.execute(query, [last_update, fn])
    db.commit()
    dt = now.strftime("%b %-d, %Y, %-I:%M%p")
    return dt

def get_ids(category):
    client.authorize()
    id_list = list()
    for obj in client.get_paged('/repositories/2/'+category):
        id = obj['uri'][obj['uri'].rfind('/')+1: ]
        id_list.append((id, obj['uri']))
    return id_list

def get_json(category, id, ancestors, digital_object, linked_agents, repository, subjects, top_container):
    client.authorize()
    uri = '/repositories/2/'+category+'/'+id
    begin = True
    if ancestors:
        uri = uri + "?resolve[]=ancestors"
        begin = False
    if digital_object:
        if begin:
            uri = uri + "?resolve[]=digital_object"
            begin = False
        else:
            uri = uri + "&resolve[]=digital_object"
    if linked_agents:
        if begin:
            uri = uri + "?resolve[]=linked_agents"
            begin = False
        else:
            uri = uri + "&resolve[]=linked_agents"
    if repository:
        if begin:
            uri = uri + "?resolve[]=repository"
            begin = False
        else:
            uri = uri + "&resolve[]=repository"
    if subjects:
        if begin:
            uri = uri + "?resolve[]=subjects"
            begin = False
        else:
            uri = uri + "&resolve[]=subjects"
    if top_container:
        if begin:
            uri = uri + "?resolve[]=top_container"
        else:
            uri = uri + "&resolve[]=top_container"
    obj = client.get(uri)
    return obj.json()

def get_ancestors(category, id):
    ancestors = list()
    obj = get_json(category, id, True, False, False, False, False, False)
    for a in obj.get('ancestors', []):
        level = a.get('level')
        if a.get('_resolved'):
            if a['_resolved'].get('title'):
                title = a['_resolved']['title']
                ancestors.append((title, level))
    return ancestors

def get_subjects(category, id):
    subjects = list()
    obj = get_json(category, id, False, False, False, False, True, False)
    for s in obj.get('subjects', []):
        if s.get('_resolved'):
            if s['_resolved'].get('title'):
                subject = s['_resolved']['title']
                if s['_resolved'].get('source'):
                    source = s['_resolved']['source']
                else:
                    source = None
                subjects.append((subject, source))
    print('subjects:', subjects)
    return subjects

def get_dates(category, id):
    dates = list()
    obj = get_json(category, id, False, False, False, False, False, False)
    for date in obj.get('dates', []):
        dates.append(date.get('expression', ''))
    return dates

def get_extents(category, id):
    extents = list()
    obj = get_json(category, id, False, False, False, False, False, False)
    for extent in obj.get('extents', []):
        extents.append(extent.get('number', '') + ' ' + extent.get('extent_type', ''))
    return extents