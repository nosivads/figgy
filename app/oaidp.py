# DIGITAL OBJECT TYPES
# list of digital objects to include in OAI output
# potential complete list: [stillimage, movingimage, sound, text, collection, software]
digital_object_type_filter = ['text', 'stillimage']

# local imports
from app.aspace import get_notes, get_last_update, write_last_update, csv_gen
from app.aspace import get_json, get_ids, get_subjects, get_extents, get_dates
from app.db import get_db
from util import defaults

# other imports
from flask import Blueprint, request, Response, render_template, send_file, g
from datetime import datetime
import pandas as pd
import xml.etree.ElementTree as ET
import xml.dom.minidom as dom
from pathlib import Path
import json, subprocess

# max number of records to return
maxrecs = defaults.maxrecs
# data provider URL
dpurl = defaults.dpurl
# base uri
idbase = defaults.idbase 
# public url
pub_url = defaults.pub_url
# collection base
cbase = defaults.cbase

bp = Blueprint('oaidp', __name__)

# namespace dictionary
ns = {'': 'http://www.openarchives.org/OAI/2.0/',
      'xlink': 'http://www.w3.org/1999/xlink',
      'dc': 'http://purl.org/dc/elements/1.1/',
      'oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/'}

# register namespaces
ET.register_namespace('', 'http://www.openarchives.org/OAI/2.0/')
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
ET.register_namespace('oai_dc', 'http://www.openarchives.org/OAI/2.0/oai_dc/')
ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')

# read static repository file
tree = ET.parse(Path(Path(__file__).resolve().parent).joinpath('../xml/staticrepo.xml'))
root = tree.getroot()

ids = list()
for node in root.findall('.//record/header/identifier', ns):
    try:
        id = int(node.text[65:])
        ids.append(id)
    except:
        pass
ids = [str(id) for id in sorted(ids)]

# returns a pretty-printed XML string
def prettify(elem):
    xml_string = ET.tostring(elem)
    xml_file = dom.parseString(xml_string)
    pretty_xml = xml_file.toprettyxml(indent="  ")
    return pretty_xml

# build OAI
@bp.route('/build')
def build():
    return render_template('build.html')

# returns a list of IDs
@bp.route('/browse/<page_number>')
def browse(page_number):
    page_number=int(page_number)
    page_size=1000
    items_total=len(ids)
    pages_total=(items_total+page_size-1)//page_size
    ids_display=ids[(page_number-1)*page_size:page_number*page_size]
    return render_template("browse.html", 
                           ids=ids_display, 
                           idbase=idbase, 
                           dpurl=dpurl,
                           page_size=page_size,
                           items_total=items_total,
                           pages_total=pages_total,
                           page_number=page_number)

# returns a record
@bp.route('/search', methods=('GET', 'POST'))
def search():
    if request.method == 'POST':
        ids = [id.text[65:] for id in root.findall('.//record/header/identifier', ns)]
        if request.form['id'] in ids:
            id = request.form['id']
        else:
            id = "id not found"
        return render_template("search.html", 
                               id=id, 
                               idbase=idbase, 
                               dpurl=dpurl)
    else:
        return render_template("search.html")

# read/write collections data to db
# display collections list
@bp.route('/collections')
def collections():
    db = get_db()
    query = 'SELECT sum(docount) as tot_docount, \
                    sum(caltechlibrary) as tot_clibrary, \
                    sum(internetarchive) as tot_iarchive, \
                    sum(youtube) tot_youtube, \
                    sum(other) as tot_other \
                FROM collections;'
    totals = db.execute(query).fetchone()
    return render_template('collections.html', 
                           output=read_colls(), 
                           dt_col=get_last_update('col'),
                           dt_xml=get_last_update('xml'),
                           url=pub_url+cbase,
                           totals=totals)

# read/write collections data to db
# display collections list
# download collections data
@bp.route('/reports', methods=['GET', 'POST'])
def reports():
    fieldnames = {  'resources' :                            
                           ['uri', 
                            'title', 
                            'suppressed',
                            'publish', 
                            'restrictions', 
                            'repository_processing_note', 
                            'ead_id', 
                            'finding_aid_title', 
                            'finding_aid_filing_title', 
                            'finding_aid_date', 
                            'finding_aid_author', 
                            'created_by', 
                            'last_modified_by', 
                            'create_time', 
                            'system_mtime', 
                            'user_mtime', 
                            'is_slug_auto', 
                            'id_0', 
                            'level', 
                            'resource_type', 
                            'finding_aid_description_rules', 
                            'finding_aid_language', 
                            'finding_aid_script',
                            'finding_aid_status', 
                            'jsonmodel_type'],
                    'accessions' : 
                           ['uri',
                            'suppressed',
                            'publish',
                            'title',
                            'display_string',
                            'content_description',
                            'provenance',
                            'general_note',
                            'accession_date',
                            'restrictions_apply',
                            'access_restrictions',
                            'use_restrictions',
                            'created_by',
                            'last_modified_by',
                            'create_time',
                            'system_mtime',
                            'user_mtime',
                            'is_slug_auto',
                            'id_0',
                            'id_1',
                            'jsonmodel_type'],
                    'digital_objects' : 
                           ['uri',
                            'digital_object_id',
                            'title',
                            'publish',
                            'restrictions',    
                            'created_by',
                            'last_modified_by',
                            'create_time',
                            'system_mtime',
                            'user_mtime',
                            'suppressed',
                            'is_slug_auto',
                            'jsonmodel_type'],
                    'archival_objects' : 
                           ['uri',
                            'position',
                            'publish',
                            'ref_id',
                            'title',
                            'display_string',
                            'restrictions_apply',
                            'created_by',
                            'last_modified_by',
                            'create_time',
                            'system_mtime',
                            'user_mtime',
                            'suppressed',
                            'is_slug_auto',
                            'level',
                            'jsonmodel_type',
                            'has_unpublished_ancestor']
                        }         
    # remove archival objects from fieldnames (TIMES OUT)
    fieldnames.pop('archival_objects', None)  
    
    if request.method == 'POST':
        category = request.form.get('category', 'resources')
        fields = request.form.getlist('include')
        filename = g.user + '_' + category + '.csv'
        if len(fields) == 0:
            fields = fieldnames[category]
        else:
            fields = [field for field in fieldnames[category] if field in fields]
        # generate CSV file
        rec_count = csv_gen(filename, fields, category)
        return render_template('reports2.html',
                                category=category,
                                filename=filename,
                                rec_count=rec_count,
                                fields=fields)
    else:
        return render_template('reports.html',
                                fieldnames=fieldnames)

# download CSV file
@bp.route('/download/<filename>')
def download(filename):
    return send_file(filename, as_attachment=True)

@bp.route('/recordidlist', methods=['GET', 'POST'])
def recordidlist():
    if request.method == 'POST':
        recordtype = request.form.get('recordtype', 'resources')
        ids = get_ids(recordtype)
        return render_template('records.html', ids=ids, recordtype=recordtype)
    else:
        return render_template('records.html')

@bp.route('/records', methods=['GET', 'POST'])
def records():
    if request.method == 'POST':
        recordtype = request.form.get('recordtype', 'resources')
        saveas = request.form.get('saveas', 'json')
        recordid = request.form.get('recordid', None)
        ancestors = request.form.get('ancestors')
        digital_object = request.form.get('digital_object')
        linked_agents = request.form.get('linked_agents')
        repository = request.form.get('repository')
        subjects = request.form.get('subjects')
        top_container = request.form.get('top_container')
        if recordid:
            obj = get_json(recordtype, recordid, ancestors, digital_object, linked_agents, repository, subjects, top_container)
            if obj is None:
                return render_template('records.html', 
                                       error='Record not found.')
            else:
                json_filename = Path(Path(__file__).resolve().parent).joinpath(g.user + '_' + recordtype + recordid + '.json')
                with open(json_filename, 'w') as file:
                    json.dump(obj, file, indent=4)
                if saveas == 'csv':
                    with open(json_filename, 'r') as file:
                        data = json.load(file)
                    df = pd.json_normalize(data)
                    #df = df.rename(columns=lambda x: x.replace('.', '_'))
                    csv_filename = Path(Path(__file__).resolve().parent).joinpath(g.user + '_' + recordtype + recordid + '.csv')
                    df.to_csv(csv_filename, index=False)
                    return send_file(csv_filename, as_attachment=True, mimetype='text/csv')
                elif saveas == 'jsonfile':
                    return send_file(json_filename, as_attachment=True, mimetype='application/json')
                elif saveas == 'json':
                    return send_file(json_filename, as_attachment=False, mimetype='application/json')
                elif saveas == 'subj':
                    subjects = get_subjects(recordtype, recordid)
                    dates = get_dates(recordtype, recordid)
                    extents = get_extents(recordtype, recordid)
                    return render_template('records.html', 
                                    subjects=subjects, 
                                    dates=dates, 
                                    extents=extents,
                                    recordtype=recordtype,
                                    recordid=recordid)
                else:
                    return render_template('records.html')
        else:
            return render_template('records.html', 
                                   error='No record ID provided.')
    else:
        return render_template('records.html')


# get total object counts
def get_total_counts():
    db = get_db()
    query = 'SELECT sum(aocount as tot_aocount, \
                    sum(docount) as tot_docount, \
                    sum(caltechlibrary) as tot_clibrary, \
                    sum(internetarchive) as tot_iarchive, \
                    sum(youtube) tot_youtube, \
                    sum(other) as tot_other \
                FROM collections;'
    return db.execute(query).fetchone()

# read collections data for display
def read_colls():
    query = 'SELECT \
                collno, \
                colltitle, \
                aocount, \
                docount, \
                caltechlibrary, \
                internetarchive, \
                youtube, \
                other, \
                incl, \
                typ, \
                last_edit, \
                type_stillimage, \
                type_text, \
                type_movingimage, \
                type_sound, \
                type_other \
             FROM collections \
             ORDER BY aocount DESC;'
    colls = get_db().execute(query).fetchall()
    # archival object total
    n0 = sum(k for (_,_,k,_,_,_,_,_,_,_,_,_,_,_,_,_) in colls)
    # digital object total
    n = sum(k for (_,_,_,k,_,_,_,_,_,_,_,_,_,_,_,_) in colls)
    return (n0, n, len(colls), colls)

# query db and update collections json file for list of ids
def update_coll_json(ids):
    db = get_db()
    # initialize dict for json output
    coll_dict = dict()
    query = "SELECT colltitle FROM collections WHERE collno=?;"
    for id in ids:
        coll_dict[id] = {'title' : db.execute(query, [id]).fetchone()[0],
                         'description' : get_notes(id)}
    # save included collections to JSON file
    with open(Path(Path(__file__).resolve().parent).joinpath('collections.json'), 'w') as f:
        json.dump(coll_dict, f)
    return

# update selected collections
@bp.route('/collections3', methods=['GET', 'POST'])
def collections3():
    db = get_db()
    if request.method == 'POST':
        db.execute('UPDATE collections SET incl=0;')
        ids = request.form.getlist('include')
        for id in ids:
            db.execute('UPDATE collections SET incl=1 WHERE collno=?;', [id])
        db.commit()
        update_coll_json(ids)
        write_last_update('col')
    totals = db.execute('SELECT total,caltechlibrary,internetarchive,youtube,other FROM totals;').fetchone()
    return render_template('collections.html', 
                           output=read_colls(), 
                           dt_col=get_last_update('col'),
                           dt_xml=get_last_update('xml'),
                           url=pub_url+cbase,
                           totals=totals)
'''
# this section provides for manual regeneration of the static repository and database update
# this has been replaced with the automatic nightly update
# the 'buildxml' code can also be run from the command line on the server

# regenerate info
@bp.route('/regen')
def regen():
    return render_template("regen.html", 
                           done=False, 
                           dt_xml=get_last_update('xml'),
                           dt_col=get_last_update('col'))

# regenerate XML
@bp.route('/regen2')
def regen2():
    codepath = Path(Path(__file__).resolve().parent).joinpath('buildxml/buildxml.py')
    subprocess.run(['python', codepath], capture_output=False)
    return render_template("regen.html", 
                           done=True, 
                           dt_xml=get_last_update('xml'),
                           dt_col=get_last_update('col'))

# run both collections (updcollinfo.py) and regen (ead2dc.py) scripts and reload server
@bp.route('/update')
def update():
    codepath = Path(Path(__file__).resolve().parent).joinpath('update.sh')
    subprocess.run(['sh', codepath], capture_output=False)
    return render_template("regen.html", 
                           done=True, 
                           dt_xml=get_last_update('xml'),
                           dt_col=get_last_update('col'))
'''
@bp.route('/search2')
def search2():
    try:
        ids = [root.find('.//record/header/identifier', ns)]
    except:
        ids = ['']
    return render_template("browse.html")

# log requests
def log(rq):
    query = "INSERT INTO logs (date, verb, setname, identifier, datefrom, dateuntil) VALUES (?, ?, ?, ?, ?, ?);"
    db = get_db()
    db.execute(query, rq)
    db.commit()
    return

# OAI data provider
@bp.route('/oai')
def oai():

    # list of collections to include
    db = get_db()
    query = "SELECT typ, collno FROM collections WHERE incl;"
    included_sets = [setid[0]+'_'+setid[1] for setid in db.execute(query).fetchall()]

    # empty list for errors
    errors = list()

    # string form of date to write to each record
    #today = date.today().strftime("%Y-%m-%d")

    # get verb from request
    verb = request.args.get('verb')
    identifier = request.args.get('identifier')
 
    # resumption token flag
    rToken = False

    if request.args.get('resumptionToken'):

        # iteration flag
        first = False

        # get resumptionToken from request and decode
        resumptionToken = request.args.get('resumptionToken').split(':')
        set_request = resumptionToken[0]
        datefrom = resumptionToken[1]
        dateuntil = resumptionToken[2]
        startrec = int(resumptionToken[3])

    else:

        # iteration flag
        first = True
    
        # get parameters from request
        set_request =  'x_000' if request.args.get('set') is None else request.args.get('set')
        datefrom = '000-00-00' if request.args.get('from') is None else request.args.get('from')
        dateuntil = '999-99-99' if request.args.get('until') is None else request.args.get('until')
        startrec = 0


    # log request
    try:
        id = identifier[identifier.rfind('/')+1:]
    except:
        id = identifier
    now = datetime.now().isoformat().split('.')[0]
    rq = [now, verb, set_request, id, datefrom, dateuntil]
    log(rq)


    # position for ListRecords/ListIdentifiers
    cursor = 0

    # records written
    count = 0


    if verb == 'Identify':

        elem = root.find('.//Identify', ns)
        # create OAI-PMH XML object
        oaixml = ET.Element('OAI-PMH')
        respDate = ET.SubElement(oaixml, 'responseDate')
        respDate.text = datetime.now().isoformat().split('.')[0]
        rquest = ET.SubElement(oaixml, 'request')
        rquest.attrib = {'verb': 'Identify'}
        rquest.text = dpurl
        identify = ET.SubElement(oaixml, 'Identify')
        for node in elem:
            identify.append(node)
        count += 1

    elif verb == 'ListMetadataFormats':

        elem = root.find('.//ListMetadataFormats', ns)
        # create OAI-PMH XML object
        oaixml = ET.Element('OAI-PMH')
        respDate = ET.SubElement(oaixml, 'responseDate')
        respDate.text = datetime.now().isoformat().split('.')[0]
        rquest = ET.SubElement(oaixml, 'request')
        rquest.text = dpurl
        listmetadataformats = ET.SubElement(oaixml, 'ListMetadataFormats')

        if identifier is None:

            rquest.attrib = {'verb': 'ListMetadataFormats'}
            for node in elem:
                listmetadataformats.append(node)
                count += 1

        else:

            rquest.attrib = {'verb': 'ListMetadataFormats', 'identifier': identifier}
            nodes = root.findall(f'.//identifier[.="{identifier}"]/../../..[@metadataPrefix]', ns)
            for node in nodes:
                prefix = node.attrib['metadataPrefix']
                mf = root.find(f'.//ListMetadataFormats/metadataFormat/metadataPrefix[.="{prefix}"]/..', ns)
                listmetadataformats.append(mf)
                count += 1

    elif verb == 'ListSets':

        elem = root.find('.//ListSets', ns)
        # create OAI-PMH XML object
        oaixml = ET.Element('OAI-PMH')
        respDate = ET.SubElement(oaixml, 'responseDate')
        respDate.text = datetime.now().isoformat().split('.')[0]
        rquest = ET.SubElement(oaixml, 'request')
        rquest.attrib = {'verb': 'ListSets'}
        rquest.text = dpurl
        listsets = ET.SubElement(oaixml, 'ListSets')
        for node in elem:
            if node.find('./setSpec', ns).text in included_sets:
                listsets.append(node)
                count = 1

    elif verb == 'ListRecords' or verb == 'ListIdentifiers':

        elem = root.find('./ListRecords', ns)
        # create OAI-PMH XML object
        oaixml = ET.Element('OAI-PMH')
        respDate = ET.SubElement(oaixml, 'responseDate')
        respDate.text = datetime.now().isoformat().split('.')[0]
        rquest = ET.SubElement(oaixml, 'request')
        rquest.attrib = {'verb': 'ListRecords',
                         'metadataPrefix': 'oai_dc'
                        }
        rquest.text = dpurl
        listrecords = ET.SubElement(oaixml, 'ListRecords')
        recrds = elem.findall('./{http://www.openarchives.org/OAI/2.0/}record')

        for recrd in recrds:

            # test for valid Type
            if recrd.find('./metadata/oai_dc:dc/dc:type', ns).text not in digital_object_type_filter:
                continue

            # get list of sets for record
            sets_list = [setnode.text for setnode in recrd.findall('./header/setSpec', ns)]

            # check 
            # - if record is in requested set, or no set specified (x_000)
            # - and if record is in included (i.e. active) sets, or user is authenticated
            if (set_request in sets_list or set_request == 'x_000') \
                    and (len(set(sets_list).intersection(set(included_sets))) > 0 \
                or g.user):

                # check if record is within date range requested
                if recrd.find('./header/datestamp', ns).text >= datefrom and \
                   recrd.find('./header/datestamp', ns).text <= dateuntil:

                    cursor += 1

                    if (cursor > startrec) and (cursor <= startrec + maxrecs):

                        count += 1

                        record = ET.SubElement(listrecords, '{http://www.openarchives.org/OAI/2.0/}record')
                        header = ET.SubElement(record, '{http://www.openarchives.org/OAI/2.0/}header')
                        hdr = recrd.find('.//{http://www.openarchives.org/OAI/2.0/}header')
                        for node in hdr:
                            header.append(node)

                        if verb == 'ListRecords':

                            metadata = ET.SubElement(record, '{http://www.openarchives.org/OAI/2.0/}metadata')
                            dc = ET.SubElement(metadata, '{http://www.openarchives.org/OAI/2.0/oai_dc/}dc')
                            metad = recrd.find('.//{http://www.openarchives.org/OAI/2.0/oai_dc/}dc')
                            for node in metad:
                                dc.append(node)

                    if cursor >= startrec + maxrecs:
                        resumptionToken = ET.SubElement(listrecords, '{http://www.openarchives.org/OAI/2.0/}resumptionToken')
                        resumptionToken.attrib = {'cursor': str(cursor)}
                        resumptionToken.text = f'{set_request}:{datefrom}:{dateuntil}:{cursor}'
                        rToken = True
                        break


        if not rToken and not first:
            resumptionToken = ET.SubElement(listrecords, '{http://www.openarchives.org/OAI/2.0/}resumptionToken')
            resumptionToken.attrib = {'cursor': str(cursor)}
                                  

    elif verb == 'GetRecord':

        if identifier is None:
            oaixml = ET.Element('noThing',)
            oaixml.text = "No identifier specified."
        else:
            # create OAI-PMH XML object
            oaixml = ET.Element('OAI-PMH')
            respDate = ET.SubElement(oaixml, 'responseDate')
            respDate.text = datetime.now().isoformat().split('.')[0]
            rquest = ET.SubElement(oaixml, 'request')
            rquest.attrib = {'verb': 'GetRecord', 'identifier': identifier, 'metaDataPrefix': 'oai_dc'}
            rquest.text = dpurl
            getrecord = ET.SubElement(oaixml, 'GetRecord')
            if root.find('./ListRecords/record/header/setSpec', ns).text in included_sets:
                try:
                    record = root.find(f'.//identifier[.="{identifier}"]/../../.', ns)
                    getrecord.append(record)
                    count += 1
                except:
                    pass
            
    else:

        oaixml = ET.Element('OAI-PMH')
        respDate = ET.SubElement(oaixml, 'responseDate')
        respDate.text = datetime.now().isoformat().split('.')[0]
        error = ET.SubElement(oaixml, 'error')
        error.text = "Missing or invalid verb or key."

    return Response(ET.tostring(oaixml), mimetype='text/xml')

