# -*- coding: utf-8 -*-
#
# buildxml.py
#
# Generates static OAI-PMH XML for Caltech Archives digital objects
# Data source is ArchivesSpace API
# Output is a single XML file: staticrepo.xml
# Only archival objects with associated digital objects are included
# An SQLite3 database, instance/ead2dc.db, is used to store collection information
# Tables: 
#   logs - logs data provider requests
#   collections - records data about collections with digital content
#   last_update - records dates of last updates of XML file and collection selection

import time
import sqlite3 as sq
import xml.etree.ElementTree as ET
import xml.dom.minidom as dom
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

# local imports
import secrets

# import ASnakeClient for ArchivesSpace API access
from asnake.client import ASnakeClient

#-----------------------------------------------------------------------#
# GLOBAL CONFIGURATION VARAIBLES

# use_statements to exclude
# 'URL-Redirected' - redirected URLs not direct links
use_exclude = ['URL-Redirected']

# hostnames to exclude
# github.com - github links are not direct links to digital content
host_exclude = ['github.com']

# maps of MODS types to Dublin Core types
# source: https://www.loc.gov/standards/mods/mods-outline-3-6.html#typeOfResource
# source: https://www.dublincore.org/specifications/dublin-core/dcmi
digital_object_type_map = {
        'still_image'                   : 'stillimage',
        'mixed_materials'               : 'collection',
        'moving_image'                  : 'movingimage',
        'notated_music'                 : 'stillimage',
        'software_multimedia'           : 'software',
        'sound_recording'               : 'sound',
        'sound_recording_musical'       : 'sound',
        'sound_recording_nonmusical'    : 'sound',
        'still_image'                   : 'stillimage',
        'text'                          : 'text'
    }

# maps of MODS relator codes to text for creator element
# source: https://www.loc.gov/marc/relators/relacode.html
relator_map = {
        'ive'                           : 'interviewee',
        'ivr'                           : 'interviewer',
        'aut'                           : 'author',
        'ctb'                           : 'contributor',
        'edt'                           : 'editor',
        'col'                           : 'collector',
        'com'                           : 'compiler',
        'con'                           : 'conservator',
        'crp'                           : 'correspondent',
        'cur'                           : 'curator',
        'dnr'                           : 'donor',
        'trc'                           : 'transcriber',
        'trl'                           : 'translator'}
 

# default resource type if none found in digital object
default_digital_object_type = 'other'

# database location
dbpath = Path(Path(__file__).resolve().parent).joinpath('../instance/ead2dc.db')

# TABLE:    collections
# COLUMNS:  collno              text    numerical id of collection, e.g. '123'
#           colltitle           text    title of collection, e.g. 'John Doe Papers'
#           description         text    description of collection  
#           collid              text    ArchivesSpace collection id, e.g. '/repositories/2/resources/123'
#           aocount             int     number of archival objects in collection
#           docount             int     number of digital objects in collection
#           incl                int     whether or not collection is published via OAI (1 = include, 0 = exclude)
#           caltechlibrary      int     number of digital objects hosted on Caltech Library servers
#           internetarchive     int     number of digital objects hosted on Internet Archive
#           youtube             int     number of digital objects hosted on YouTube
#           other               int     number of digital objects hosted on other servers
#           typ                 text    collection type: 'resource' or 'accession'
#           type_text           int     number of digital objects of type 'text'
#           type_stillimage     int     number of digital objects of type 'stillImage'
#           type_movingimage    int     number of digital objects of type 'movingImage'
#           type_sound          int     number of digital objects of type 'sound'
#           type_other          int     number of digital objects of other types
#           last_edit           text    date of last edit to collection record (from previous build)

# query to insert collection records into db
dbq_collections_insert = 'INSERT INTO collections \
                                    ( \
                                    collno, \
                                    colltitle, \
                                    description, \
                                    collid, \
                                    aocount, \
                                    docount, \
                                    incl, \
                                    caltechlibrary, \
                                    internetarchive, \
                                    youtube, \
                                    other, \
                                    typ, \
                                    type_text, \
                                    type_stillimage, \
                                    type_movingimage, \
                                    type_sound, \
                                    type_other \
                                    ) \
                                VALUES \
                                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);'

# query to read collection info from db
qdb_collections_select = 'SELECT    collno, \
                                    colltitle, \
                                    description, \
                                    collid, \
                                    aocount, \
                                    docount, \
                                    incl, \
                                    caltechlibrary, \
                                    internetarchive, \
                                    youtube, \
                                    other, \
                                    typ, \
                                    type_text, \
                                    type_stillimage, \
                                    type_movingimage, \
                                    type_sound, \
                                    type_other \
                                FROM collections;'

# default rights statement to include in XML records
default_rights_statement = 'The copyright and related rights status of this Item has not been evaluated. \
Please contact Caltech Archives and Special Collections for more information. You are free to use this \
Item in any way that is permitted by the copyright and related rights legislation that applies to your use.'

#-----------------------------------------------------------------------#
# FUNCTIONS (in order of appearance)
#
#   authorize_api()                             establish API connection
#
#   prettify(elem)                              returns a "pretty" XML string 
#                                               from an ElementTree Element
#
#   create_collection_description(coll_info)    create collection description string from 
#                                               collection notes in ArchivesSpace
#                                               used to compile dc:description element in 
#                                               OAI-PMH setDescription
#
#   build_collections_dict()                    builds two dictionaries: for collections and archival objects
#                                               collections_dict has the form {collection: {ao: {do}}}
#                                               archival_objects_dict has the form 
#                                               {ao: {'collections': [collection], 'digital_objects': [do]}}
#
#   create_valid_hostnames_set(file_uris)       removes invalid hostnames from file_uris list and 
#                                               returns set of valid hostnames
#
#   get_domain_from_url(file_url)               extracts domain from url
#
#   published_file_uris(do_list)                returns list of published file URIs and use statements from 
#                                               digital objects in do_list. do_list is a list of digital object URIs
#                                               returns list of tuples: (file_uri, use_statement)
#
#   get_set_id(collection_id)                   converts collection id to set id
#
#   get_digital_object_type(do_list)            returns list of digital object types from digital objects in do_list
#                                               uses digital_object_type_map to map ArchivesSpace types to Dublin Core types
#-----------------------------------------------------------------------#

# establish API connection
def authorize_api():
    client = ASnakeClient(baseurl = secrets.baseurl,
                        username = secrets.username,
                        password = secrets.password)
    client.authorize()
    return client

#-----------------------------------------------------------------------#

# returns a "pretty" XML string from an ElementTree Element (xml.etree.ElementTree.Element)
def prettify(elem):
    xml_string = ET.tostring(elem)
    xml_file = dom.parseString(xml_string)
    pretty_xml = xml_file.toprettyxml(indent="  ")
    return pretty_xml

#-----------------------------------------------------------------------#

# create collection description string from collection notes in ArchivesSpace
# used to compile dc:description element in OAI-PMH setDescription
def create_collection_description(coll_info):

    try:
        description = [note for note in coll_info['notes'] if (note['type'] == 'scopecontent' or note['type'] == 'abstract') and note['publish']]
    except:
        description = None
    if description:
        try:
            notepart1 = ' '.join([note['content'][0] for note in description if note['jsonmodel_type'] == 'note_singlepart'])
        except:
            notepart1 = ''
        try:
            notepart2 = ' '.join([note['subnotes'][0]['content'] for note in description if note['jsonmodel_type'] == 'note_multipart'])
        except:
            notepart2 = ''
        description = notepart1 + ' ' + notepart2
    else:
        description = ''

    return description.strip()

#-----------------------------------------------------------------------#

# builds two dictionaries: for collections and archival objects
# collections_dict has the form {collection: {ao: {do}}}
# archival_objects_dict has the form {ao: {'collections': [collection], 'digital_objects': [do]}}
def build_collections_dict(client):

    # initialize collections dictionary
    # this dictionary references archival objects with related digital objects
    collections_dict = dict()
    # initialize collections set
    collections = set()

    # iterate over digital objects
    digital_objects = client.get_paged('/repositories/2/digital_objects')

    n = 0

    for obj in digital_objects:

        n += 1
        print (n, end='\r')

        do = obj['uri']

        # only include objects that are published and not suppressed
        if obj.get('publish') == True and obj.get('suppressed') == False:

            # capture the id of the collections
            colls_list = obj.get('collection')

            if colls_list:

                # iterate over the linked instances to find archival records
                for linked_instance in obj['linked_instances']:

                    # if linked to an archival object
                    if linked_instance['ref'][:33] == '/repositories/2/archival_objects/':

                        ao = linked_instance['ref']

                        # build dictionary of collections, digital objects, and archival objects
                        # dict has the form {collection: {ao: {do}}}
                        # ao: 'archival object' is an id
                        # do: 'digital object' is an id
                        for collection in colls_list:

                            # add to collections set
                            coll = collection['ref']
                            collections.add(coll)
            
                            if collections_dict.get(coll):

                                # add to existing collection
                                if collections_dict[coll].get(ao):

                                    # add digital object to existing archival object
                                    collections_dict[coll][ao].append(do)

                                else:

                                    # create new archival object entry
                                    collections_dict[coll][ao] = [do]

                            else:

                                # create new collection
                                collections_dict[coll] = {ao: [do]}

    print('Done building collections dictionary...')

    # convert collections dictionary to archival objects dictionary
    # form: {ao: {'collections': [collection], 'digital_objects': [do]}}

    # initialize archival objects dictionary
    archival_objects_dict = dict()

    n = 0

    for collection, ao_dict in collections_dict.items():

        n += 1
        print (n, end='\r')

        for ao, do_list in ao_dict.items():

            if archival_objects_dict.get(ao):

                archival_objects_dict[ao]['collections'].append(collection)
                archival_objects_dict[ao]['digital_objects'].extend(do_list)

            else:

                archival_objects_dict[ao] = {'collections': [collection], 'digital_objects': do_list}

    print('Done building archival objects dictionary...')


    return collections_dict, archival_objects_dict


#-----------------------------------------------------------------------#

# removes invalid hostnames from file_uris list and returns set of valid hostnames
def create_valid_hostnames_set(file_uris):
    
    hostnames = {get_domain_from_url(file_uri[0]) for file_uri in file_uris}

    # remove excluded
    for host in host_exclude:
        hostnames.discard(host)

    return hostnames


#-----------------------------------------------------------------------#

# extracts domain from url
def get_domain_from_url(file_url):
    
    # parse url
    hostname = urlparse(file_url).netloc
    # remove port if present
    hostname = hostname.split(':')[0]
    # get last two segments for domain
    hostname = hostname.split('.')[-2:]
    # reassemble hostname  
    domain = '.'.join(hostname)

    return domain  

#-----------------------------------------------------------------------#

# returns list of published file URIs and use statements from digital objects in do_list
# do_list is a list of digital object URIs
# returns list of tuples: (file_uri, use_statement)
def published_file_uris(client, do_list):

    # create file_uris set
    file_uris = set()

    # iterate over digital objects linked to archival object
    for do in do_list:

        # get digital object metadata
        obj = client.get(do).json()

        # iterate over file versions
        for file_version in obj['file_versions']:

            # only include published file versions with use statements not in exclude list
            # use default use statement of 'Web-Access' if none present
            if file_version.get('publish') and file_version.get('use_statement', 'Web-Access') not in use_exclude:
                file_uris.add((file_version['file_uri'], file_version.get('use_statement', 'Web-Access')))
                
        # check for representative file version
        if obj.get('representative_file_version'):
            rfv = obj['representative_file_version']

            # only include published representative file version with use statement not in exclude list
            # use default use statement of 'Web-Access' if none present
            if rfv.get('publish') and rfv.get('use_statement', 'Web-Access') not in use_exclude:
                file_uris.add((rfv['file_uri'], rfv.get('use_statement', 'Web-Access')))

    # de-duplicate and sort file_uris list
    file_uris = list(set(file_uris))
    file_uris.sort()

    # limit to http or https urls
    file_uris = [file_uri for file_uri in file_uris if urlparse(file_uri[0]).scheme in ['http', 'https']]

    # check for duplicate urls
    # using enumerate and list copies to allow removal during iteration
    for index, (f1, f2) in enumerate(zip(list(file_uris), list(file_uris[1:]))):

        # if duplicate urls with different 'Persistent-URL' and 'Web-Access' use statements, remove 'Persistent-URL' entry
        # assumes list is sorted and deduped (as above)
        # additional logic can be added here to handle other duplicates as needed
        if f1[0] == f2[0] \
            and f1[1]=="Persistent-URL" \
            and f2[1]=="Web-Access":
            file_uris.pop(index)

    return file_uris                    


#-----------------------------------------------------------------------#

# converts collection id to set id
def get_set_id(collection_id):

    id_list = collection_id.split('/')
    collection_type = id_list[-2][:-1]
    collection_number = id_list[-1]
    setid = collection_type + '_' + collection_number

    return setid


#-----------------------------------------------------------------------#

# returns list of digital object types from digital objects in do_list
def get_digital_object_type(client, do_list):

    # ArchivesSpace digital_object_type_values
    # mapped to Dublin Core types
    # source: https://www.dublincore.org/specifications/dublin-core/dcmi-terms/
    # DC Type Vocabulary:
    #     Collection, Dataset, Event, Image, InteractiveResource,
    #     MovingImage, PhysicalObject, Service, Software, Sound,
    #     StillImage, Text
    # create list of types
    type_list = [client.get(do).json().get('digital_object_type') for do in do_list]

    # de-duplicate
    type_list = list(set(type_list))

    # map values to dc:type
    type_list = [digital_object_type_map.get(t) for t in type_list]

    # remove None values
    type_list = [t for t in type_list if t is not None]

    if type_list == []:
        return [default_digital_object_type]
    else:
        return type_list


#-----------------------------------------------------------------------#

# refresh collections information to database from collections dictionary
def database_refresh(client, collections_dict, runtype):

    # open database connection
    connection = sq.connect(dbpath)
    cursor = connection.cursor()

    # retrieve earliest date stamp from previous build
    query = 'SELECT earliest FROM dates;'
    result = cursor.execute(query)
    earliestDatestamp = result.fetchone()[0]

    # retrieve included collections from db
    # return dictionary of collection numbers and inclusion status
    includedcollections = dict()
    query = 'SELECT collno,incl FROM collections;'
    for row in cursor.execute(query).fetchall():
        includedcollections[row[0]] = row[1]
    
    if runtype == 'production':

        # delete all records from db
        query = 'DELETE FROM collections;'
        cursor.execute(query)

    # iterate over collections dictionary to insert collection records into db
    print ('Collections with digital objects...')
    for collection in collections_dict:

        # get collection info
        coll_info = client.get(collection).json()

        # create collection description from collection notes in ArchivesSpace
        collid = coll_info['uri']
        colltitle = coll_info['title']
        description = create_collection_description(coll_info)

        # initialize sets to count unique digital objects and archival objects
        coll_dos, coll_aos = set(), set()

        # extract collection type and number from collection id
        if collid[16:25] == 'resources':
            colltyp = 'resource'
            collno = collid[26:]
        else:
            colltyp = 'accession'
            collno = collid[27:]

        # iterate over collection to count unique digital objects and archival objects
        for ao in collections_dict[collection]:
            coll_aos.add(ao)
            for do in collections_dict[collection][ao]:
                coll_dos.add(do)

        if runtype == 'production':
        
            # insert collection record into db
            cursor.execute(dbq_collections_insert, 
                           [collno,                              # collno (str)
                            colltitle,                           # colltitle (str)
                            description,                         # description (str)                 
                            collid,                              # collid (str) 
                            0,                                   # aocount (int) 
                            0,                                   # docount (int) 
                            includedcollections.get(collno, 0),  # incl (Boolean) 
                            0,                                   # caltechlibrary (int)
                            0,                                   # internetarchive (int)
                            0,                                   # youtube (int) 
                            0,                                   # other (int) 
                            colltyp,                             # typ ('resource'|'accession')
                            0,                                   # type_text (int)
                            0,                                   # type_stillimage (int)
                            0,                                   # type_movingimage (int)
                            0,                                   # type_sound (int)
                            0                                    # type_other (int)
                            ])
    
        # print collection summary
        print('>', client.get(collection).json()['title'],
            '(' + str(len(coll_aos)) + ' archival objects; ' + str(len(coll_dos)) +  ' digital objects' + ')')

    if runtype == 'production':
        # commit changes to db before reading
        connection.commit()

    # colls is a list of tuples: {(collno, colltitle, description, collid, aocount, docount, incl,
    #                             caltechlibrary, internetarchive, youtube, other, typ,
    #                             type_text, type_stillimage, type_movingimage, type_sound, type_other)}
    colls = cursor.execute(qdb_collections_select).fetchall()
    cursor.close()
    connection.close()

    return colls, earliestDatestamp


#-----------------------------------------------------------------------#

# update collections
def database_update(stats_dict, coll_mdate_dict):

    connection = sq.connect(dbpath)
    db = connection.cursor()

    for collid, values in stats_dict.items():
        query = 'UPDATE collections SET aocount=? WHERE collid=?;'
        db.execute(query, [values['archival_objects'], collid])

        do_count = 0
        for category, count in values['digital_objects'].items():
            do_count += count
            query = 'UPDATE collections SET '+category+'=? WHERE collid=?;'
            db.execute(query, [count, collid])

        query = 'UPDATE collections SET docount=? WHERE collid=?;'
        db.execute(query, [do_count, collid])

        for type_value, count in values.get('types', {}).items():
            query = 'UPDATE collections SET type_'+type_value.lower()+'=? WHERE collid=?;'
            db.execute(query, [count, collid])

    # update last modified date by collection in db
    query = 'UPDATE collections SET last_edit=? WHERE collid=?;'
    today = date.today().strftime('%Y-%m-%d')
    for collid, mod_date in coll_mdate_dict.items():
        db.execute(query, [mod_date, collid])
        earliestDatestamp = min(today, mod_date)

    query = 'UPDATE dates SET earliest = ?'
    db.execute(query, [earliestDatestamp])

    # write ISO last update
    now = datetime.now()
    last_update = now.isoformat()
    query = 'UPDATE last_update SET dt=? WHERE fn=?;'
    db.execute(query, [last_update, 'xml'])

    db.close()
    connection.commit()
    connection.close()

    return


#-----------------------------------------------------------------------#
# START OF SCRIPT 
# 
# Contents
# 
# 1. ESTABLISH API CONNECTION
# 2. BUILD COLLECTIONS DICTIONARIES
# 3. READ/WRITE COLLECTION DATA TO DATABASE FROM ARCHIVESSPACE
# 4. BUILD OAI-PMH XML OBJECT (oaixml)
# 5. UPDATE DATABASE
# 6. WRITE XML TO DISK
#-----------------------------------------------------------------------#

def main():

    #-----------------------------------------------------------------------#
    # RUNTYPE VARAIBLES

    # set -r to 'test' or 'dev' or anything except 'production' for test or development runs
    # default -r is 'production'
    # set -n to limit number of records processed (for testing)
    # default -n is 1000 for development runtype
    # default -n is all records for production runtype
    # stats are not updated when runtype != 'production'
    # output xml file is staticrepo_test.xml for test or development runtype
    # output xml file is staticrepo.xml for production runtype

    # Initialize parser
    parser = argparse.ArgumentParser()
    parser.add_argument('-r', '--runtype', default='production')
    parser.add_argument('-n', '--num_recs', default=-1, type=int)

    # Read arguments from command line
    args = parser.parse_args()
    runtype = args.runtype
    num_recs = args.num_recs

    if runtype == 'production':
        print('Running in production mode...')
        print('Processing all records...')
        xml_output_path = Path(Path(__file__).resolve().parent).joinpath('../xml/staticrepo.xml')
        dup_output_path = Path(Path(__file__).resolve().parent).joinpath('../xml/duplicates.txt')

    else:
        print('Running in', runtype, 'mode...')
        if num_recs < 0:
            num_recs = 1000
        print('Limiting to', num_recs, 'records for testing...')
        xml_output_path = Path(Path(__file__).resolve().parent).joinpath('../dev/staticrepo.xml')
        dup_output_path = Path(Path(__file__).resolve().parent).joinpath('../dev/duplicates.txt')

    start = time.time()

    #-----------------------------------------------------------------------#
    # 1. ESTABLISH API CONNECTION
    #-----------------------------------------------------------------------#
    
    print('Authorizing API...')
    client = authorize_api()

    #-----------------------------------------------------------------------#
    # 2. BUILD COLLECTIONS DICTIONARIES
    #-----------------------------------------------------------------------#
    # builds two dictionaries: for collections and archival objects
    # collections_dict has the form {collection: {ao: {do}}}
    # archival_objects_dict has the form {ao: {'collections': [collection], 'digital_objects: [do]}}

    print('Building collections dictionary...')
    collections_dict, archival_objects_dict = build_collections_dict(client)

    #-----------------------------------------------------------------------#
    # 3. READ/WRITE COLLECTION DATA TO DATABASE FROM ARCHIVESSPACE
    #-----------------------------------------------------------------------#
    # db location
    # relevant tables in database:
    #   collections - records data about collections with digital content
    #   dates - records dates of last updates of XML file and collection selection
    #   logs - logs data provider requests (used in oaidp.py)

    print('Refreshing database...')
    colls, earliestDatestamp = database_refresh(client, collections_dict, runtype)
    
    #-----------------------------------------------------------------------#
    # 4. BUILD OAI-PMH XML OBJECT (oaixml)
    #-----------------------------------------------------------------------#

    print('Building static repository...')

    # namespace dictionary
    ET.register_namespace('', 'http://www.openarchives.org/OAI/2.0/')
    ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
    ET.register_namespace('oai_dc', 'http://www.openarchives.org/OAI/2.0/oai_dc/')
    ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')

    # create OAI-PMH XML object
    oaixml = ET.Element('OAI-PMH', {'xmlns':'http://www.openarchives.org/OAI/2.0/',
        'xmlns:xsi':'http://www.w3.org/2001/XMLSchema-instance',
        'xsi:schemaLocation':'http://www.openarchives.org/OAI/2.0/ http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd'})

    # build Identify segment
    Identify = ET.SubElement(oaixml, 'Identify')
    repositoryName = ET.SubElement(Identify, 'repositoryName')
    repositoryName.text = 'Caltech Archives Digital Collections'
    baseURL = ET.SubElement(Identify, 'baseURL')
    baseURL.text = 'http://apps.library.caltech.edu/ead2dc/oai'
    protocolVersion = ET.SubElement(Identify, 'protocolVersion')
    protocolVersion.text = '2.0'
    adminEmail = ET.SubElement(Identify, 'adminEmail')
    adminEmail.text = 'archives@caltech.edu'
    earliestDate = ET.SubElement(Identify, 'earliestDatestamp')
    earliestDate.text = earliestDatestamp
    deletedRecord = ET.SubElement(Identify, 'deletedRecord')
    deletedRecord.text = 'no'
    granularity = ET.SubElement(Identify, 'granularity')
    granularity.text = 'YYYY-MM-DD'

    # build ListMetadataFormats segment
    ListMetadataFormats = ET.SubElement(oaixml, 'ListMetadataFormats')
    metadataFormat = ET.SubElement(ListMetadataFormats, 'metadataFormat')
    metadataPrefix = ET.SubElement(metadataFormat, 'metadataPrefix')
    metadataPrefix.text = "oai_dc"
    schema = ET.SubElement(metadataFormat, 'schema')
    schema.text = "http://www.openarchives.org/OAI/2.0/oai_dc.xsd"
    metadataNamespace = ET.SubElement(metadataFormat, 'metadataNamespace')
    metadataNamespace.text = "http://www.openarchives.org/OAI/2.0/oai_dc/"

    # build ListSets segment
    ListSets = ET.SubElement(oaixml, 'ListSets')
                            
    for coll in colls:
        oaiset = ET.SubElement(ListSets, 'set')
        setSpec = ET.SubElement(oaiset, 'setSpec')
        setSpec.text = coll[11]+'_'+coll[0]
        setName = ET.SubElement(oaiset, 'setName')
        setName.text = coll[1]
        setDescription = ET.SubElement(
            ET.SubElement(
                ET.SubElement(oaiset, 'setDescription'), 'oai_dc', {
                        'xmlns:oai_dc':'http://www.openarchives.org/OAI/2.0/oai_dc/',
                        'xmlns:dc':'http://purl.org/dc/elements/1.1/',
                        'xmlns:xsi':'http://www.w3.org/2001/XMLSchema-instance',
                        'xsi:schemaLocation':'http://www.openarchives.org/OAI/2.0/oai_dc/ http://www.openarchives.org/OAI/2.0/oai_dc.xsd'
                }
            ), 'dc:description'
        )
        setDescription.text = coll[2]

    # build ListRecords segment
    ListRecords = ET.SubElement(oaixml, 'ListRecords', {'metadataPrefix': 'oai_dc'})

    # initialize stats_dict for collection statistics
    # {setid: {'archival_objects': #, 'digital_objects': {hostcategory: #}, 'types': {type: #}}
    stats_dict = dict()

    # initialize coll_mdate_dict to track most recently modified record by collection
    # {collid: 'mdate'}
    coll_mdate_dict = dict()

    # iterate over archival object dictionary
    # do = digital object, ao = archival object
    # archival_objects_dict = {ao: {'collections': [collids], 'digital_objects: [dos]}}        
    j = 0

    # initialize set to check for duplicate uris
    file_uri_set, duplicate_uris_set = set(), set()

    for ao, colls_dict in archival_objects_dict.items():

        # display archival object id
        print(ao, '   ', end='\r')

        # limit number of records processed if testing
        if runtype != 'production':
            j += 1
            if j > num_recs:
                break

        # get archival object metadata
        uri = ao + "?resolve[]=ancestors" \
                + "&resolve[]=digital_object" \
                + "&resolve[]=linked_agents" \
                + "&resolve[]=repository" \
                + "&resolve[]=subjects" \
                + "&resolve[]=top_container"
        archival_object_metadata = client.get(uri).json()

        # string form of date to write to each record
        create_time = archival_object_metadata['create_time']
        system_mtime = archival_object_metadata['system_mtime']
        user_mtime = archival_object_metadata['user_mtime']
        last_modified_date = max([create_time, system_mtime, user_mtime])[:10]

        # create list of associated digital objects
        do_list = colls_dict['digital_objects']

        # remove unpublished, redirects
        file_uris = published_file_uris(client, do_list)

        # skip archival object if no published digital object file URIs
        if len(file_uris) == 0:
            continue
        
        # skip archival object if duplicate uri
        dup = False
        for file_uri in file_uris:
            if file_uri in file_uri_set:
                duplicate_uris_set.add(file_uri)
                dup = True
            else:
                file_uri_set.add(file_uri)
        if dup:
            continue

        # create hostnames set
        hostnames = create_valid_hostnames_set(file_uris)

        # record element
        record = ET.SubElement(ListRecords, 'record')

        # header element
        header = ET.SubElement(record, 'header')

        identifier = ET.SubElement(header, 'identifier')
        identifier.text = 'collections.archives.caltech.edu' + ao
        #identifier.attrib = {'type': 'archival'}

        # datestamp element
        datestamp = ET.SubElement(header, 'datestamp')
        datestamp.text = last_modified_date

        # setSpec element
        for collid in colls_dict['collections']:

            setspec = ET.SubElement(header, 'setSpec')
            setspec.text = get_set_id(collid)

            # add archival record to stats_dict
            # {collid: {'archival_objects': #, 'digital_objects': {hostcategory: #}}
            if stats_dict.get(collid):
                stats_dict[collid]['archival_objects'] += 1
            else:
                stats_dict[collid] = {'archival_objects': 1, 'digital_objects': dict(), 'types': dict()}

            # track last modified date by collection
            if coll_mdate_dict.get(collid):
                if last_modified_date > coll_mdate_dict[collid]:
                    coll_mdate_dict[collid] = last_modified_date
            else:
                coll_mdate_dict[collid] = last_modified_date

        # create metadata element
        metadata = ET.SubElement(record, 'metadata')

        # dc element
        dc = ET.SubElement(metadata, 'oai_dc:dc', {'xmlns:oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/',
                                            'xmlns:dc': 'http://purl.org/dc/elements/1.1/',
                                            'xmlns:dcterms': 'http://purl.org/dc/terms/'})
        
        title = ET.SubElement(dc, 'dc:title')
        title.text = archival_object_metadata['title']
        #title.attrib = {'type': 'archival'}

        # creators, subjects
        creators = list()
        subjects = list()
        for linked_agent in archival_object_metadata.get('linked_agents', []):
            if linked_agent.get('role') == 'creator':
                if linked_agent.get('_resolved'):
                    name = linked_agent['_resolved'].get('title')
                    role = relator_map.get(linked_agent.get('relator'), None)
                    if role:
                        name = name + ', ' + relator_map[linked_agent.get('relator')]
                    creators.append(name)
            if linked_agent.get('role') == 'subject':
                if linked_agent.get('_resolved'):
                    name = linked_agent['_resolved'].get('title')
                    subjects.append((name, None))
 
        for c in creators:
            creator = ET.SubElement(dc, 'dc:creator')
            creator.text = c

        # subjects
        for s in archival_object_metadata.get('subjects', []):
            if s.get('_resolved'):
                source = s['_resolved'].get('source')
                if s['_resolved'].get('title'):
                    subject = s['_resolved']['title']
                    subjects.append((subject, source))

        for s in subjects:
            if s:
                subject = ET.SubElement(dc, 'dc:subject')
                subject.text = s[0]
                if s[1]:
                    subject.attrib = {'source': s[1]}
        
        # description, rights
        # list to capture rights info from userestrict note
        # format: list of tuples [(level, content)]
        # levels are in order of preference: 'x_item', 'subseries', 'series', 'collection'
        rights = list()
        for note in archival_object_metadata.get('notes', []):

            if note.get('publish') and (note['type'] == 'scopecontent' or note['type'] == 'abstract'):
                if note['jsonmodel_type'] == 'note_singlepart':
                    desc_text = note['content'][0]
                elif note['jsonmodel_type'] == 'note_multipart':
                    desc_text = note['subnotes'][0]['content']

                description = ET.SubElement(dc, 'dc:description')
                description.text = desc_text

            if note.get('publish') and (note['type'] == 'userestrict'):
                if note['jsonmodel_type'] == 'note_singlepart':
                    item_rights_note = note['content'][0]
                elif note['jsonmodel_type'] == 'note_multipart':
                    item_rights_note = note['subnotes'][0]['content']

                # capture item rights info for use below
                rights.append(('x_item', item_rights_note))
                
                '''
                # optional description attribute
                description.attrib = {'type': 'scopecontent' if note['type']=='scopecontent' else 'abstract',
                                      'label': 'Scope and Content' if note['type']=='scopecontent' else 'Abstract'}
                '''

        for file_uri in file_uris: 

            # parse url
            hostname = get_domain_from_url(file_uri[0])

            # skip excluded hostnames
            if hostname not in hostnames:
                continue

            # categorize hostname
            if hostname in ['caltech.edu', 'californiarevealed.org']:
                hostcategory = 'caltechlibrary'
            elif hostname == 'archive.org':
                hostcategory = 'internetarchive'
            elif hostname in ['youtube.com', 'youtu.be']:
                hostcategory = 'youtube'
            else:
                hostcategory = 'other'

            # identifier element
            # unpack tuple
            f_uri, f_use = file_uri
            identifier = ET.SubElement(dc, 'dc:identifier')
            identifier.text = f_uri
            identifier.attrib = {'scheme': 'URI', 'type': f_use if f_use else 'unknown'}

            # omit thumbnail links from statistics
            if 'thumbnail' in f_use.lower():
                continue

            for collid in colls_dict['collections']:

                if stats_dict[collid].get('digital_objects'):

                    if stats_dict[collid]['digital_objects'].get(hostcategory):
                        stats_dict[collid]['digital_objects'][hostcategory] += 1

                    else:
                        stats_dict[collid]['digital_objects'][hostcategory] = 1

                else:
                    stats_dict[collid]['digital_objects'][hostcategory] = 1

        # identifier element
        if archival_object_metadata.get('component_id'):
            identifier = ET.SubElement(dc, 'dc:identifier')
            identifier.text = archival_object_metadata['component_id']
            identifier.attrib = {'type': 'localid'}

        # dates
        for dt in archival_object_metadata.get('dates', []):

            if dt.get('expression'):
                date_expression = dt['expression']
            else:
                date_expression = ''
                if dt.get('begin'):
                    date_expression += dt['begin']
                if dt.get('end'):
                    if date_expression != '':
                        date_expression += ' - '
                    date_expression += dt['end']

            if date_expression:
                date_elem = ET.SubElement(dc, 'dc:date')
                date_elem.text = date_expression
                attribs = dict()
                if dt.get('begin'):
                    attribs['begin'] = dt['begin']
                if dt.get('end'):
                    attribs['end'] = dt['end']
                if dt.get('date_type'):
                    attribs['type'] = dt['date_type']
                if dt.get('label'):
                    attribs['label'] = dt['label']
                if dt.get('certainty'):
                    attribs['certainty'] = dt['certainty']
                if attribs != dict():
                    date_elem.attrib = attribs

        # type
        for type_value in get_digital_object_type(client, do_list):
            type_el = ET.SubElement(dc, 'dc:type')
            type_el.text = type_value

            # add type to stats_dict
            # {setid: {'types': {type_value: #}}
            if stats_dict[collid].get('types'):
                if stats_dict[collid]['types'].get(type_value):
                    stats_dict[collid]['types'][type_value] += 1
                else:
                    stats_dict[collid]['types'][type_value] = 1
            else:
                stats_dict[collid]['types'][type_value] = 1

        # extents
        extents = list()
        for extent in archival_object_metadata.get('extents', []):
            s = extent.get('number', '') + ' ' + extent.get('extent_type', '') + ' ' + extent.get('physical_details', '').strip()
            extents.append(s)

        for e in extents:
            if e.strip() != '':
                extent = ET.SubElement(dc, 'dc:format')
                extent.text = e.strip()

        # relation, rights
        ancestors = list()
        for a in archival_object_metadata.get('ancestors', []):
            level = a.get('level')

            if a.get('_resolved'):
                if a['_resolved'].get('title'):
                    title = a['_resolved']['title']
                    ancestors.append((level, title))

                if a['_resolved'].get('notes'):
                    nn = a['_resolved']['notes']
                    for n in nn:
                        if n.get('type'):
                            if n['type']=='userestrict':
                                if n['jsonmodel_type']=='note_singlepart':
                                    content = ' '.join(n['content'])
                                else:
                                    content = n['subnotes'][0]['content']
                                rights.append((level, content))

        # relation
        for a in ancestors:
            if a:
                ancestor = ET.SubElement(dc, 'dc:relation')
                ancestor.text = a[1]
                if a[1]:
                    ancestor.attrib = {'level': a[0]}
        
        # rights
        # sort order: 'x_item', 'subseries', 'series', 'collection'
        rights.sort(reverse=True)

        rights_el = ET.SubElement(dc, 'dc:rights')

        ok = False

        for r in rights:
            if r[1]:
                rights_el.text = r[1]
                ok = True
                break

        if not ok:

            rights_el.text = default_rights_statement

    #-----------------------------------------------------------------------#
    # 5. UPDATE DATABASE
    #-----------------------------------------------------------------------#
    # update collection statistics in db
    # {collid: {'archival_objects': #, 'digital_objects': {hostcategory: #}}

    if runtype == 'production':

        print('Updating database...')
        database_update(stats_dict, coll_mdate_dict)

    #-----------------------------------------------------------------------#
    # 6. WRITE XML TO DISK
    #-----------------------------------------------------------------------#

    # write XML to disk
    with open(xml_output_path, 'w') as f:
        f.write(prettify(oaixml))

    # write duplicate URI report
    # duplicate_uris_set is a set of tuples
    
    with open(dup_output_path, 'w') as f:
        for uri_tuple in duplicate_uris_set:
            out = uri_tuple[0] + ' (' + uri_tuple[1] + ')\n'
            f.write(out)
    
    # print elapsed time in seconds (about 75 mins)
    elapsed_time = timedelta(seconds=time.time()-start)
    print('Total elapsed time:', elapsed_time, 50*' ')

    print('Done.')

#-----------------------------------------------------------------------#


if __name__ == '__main__':
    main()
