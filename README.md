# An OAI Static Repository and Data Provider for ArchivesSpace

There are two components to this service:

* A Python 3 script, [buildxml.py](util/buildxml.py), to build an [Open Archives Initiative](https://www.openarchives.org/pmh/) (OAI) [Static Repository](https://www.openarchives.org/OAI/2.0/guidelines-static-repository.htm) from an ArchivesSpace (AS) repository using the AS API.  
* A Flask [web application](app/) that implements an OAI Data Provider to provide access to records in the Static Repository.
* The name of this repository, [ead2dc](https://github.com/caltechlibrary/ead2dc), is a misnomer, referring to a former version that transformed AS EAD output to generate the static repository.


[![License](https://img.shields.io/badge/License-BSD--like-lightgrey)](https://choosealicense.com/licenses/bsd-3-clause)


## Table of contents

* [Introduction](#introduction)
* [Installation and Usage](#installation-and-usage)
  * [buildxml](#database)
  * [Data Provider](#data-provider)
  * [Database](#database)
  * [Default Values](#default-values)
* [License](#license)
* [References](#references)
* [Acknowledgments](#acknowledgments)


## Introduction

The Python 3 script, [buildxml.py](util/buildxml.py), connects with a specific ArchivesSpace repository via the AS API, scans the digital objects in the repository, finds the associated archival objects, and writes the OAI Static Repository XML file. The XML output contains Dublin Core (DC) records for digital resources. The XML static repository is based on the [OAI Static Repository specification](https://www.openarchives.org/OAI/2.0/guidelines-static-repository.htm), but does not adhering to it strictly. The static repository is the data source for the Open Archives Initiative (OAI) Data Provider.

The [OAI Data Provider](https://apps.library.caltech.edu/ead2dc/) adheres to the OAI standard and supports all the verbs (Identify, ListMetadataFormats, ListSets, ListIdentifiers, ListRecords, and GetRecord), resumption tokens, and sets. Only DC metadata is provided. Sets correspond to the archival collections in the Caltech Archives.

Main features and assumptions:

* The OAI Data Provider uses a static repository, i.e. it does not dynamically generate records. The behavior of the Data Provider is, however, indistinguishable from a dynamic provider, except for the currency of the data. In the Caltech Library implementation the static repository is rewritten automatically once per day.
* The output of the Data Provider is OAI-compliant, as tested using this [OAI-PMH Validator](https://validator.oaipmh.com/).
* Only digital objects are included. Archival objects without digital content are omitted.
* Descriptive metadata is drawn from the archival object associated with each digital object.
* Only Dublin Core metadata is supported. Other metadata formats are not currently supported.
* Sets correspond to the AS archival collections (resources). A single record can belong to more than one set (i.e. be represented in more than one collection).
* The data provider returns records in batches of 250. A resumption token is provided to request each subsequent page.

## Installation and Usage

### buildxml

The [buildxml.py](util/buildxml.py) file is designed to be run from the command line, or from within your favorite editing environment. It uses standard Python libraries and has been tested using Python 3.12.

Installation of the [ArchivesSnake client library](https://github.com/archivesspace-labs/ArchivesSnake) is required to utilize the ArchivesSpace backend API. It can be installed using 
```
pip3 install ArchivesSnake
```
Other required packages are all standard Python.

To generate the static XML repository run the script in the same location as the defaults.py and secrets.py files:
```
python buildxml.py
```
[defaults.py](util/defaults_template.py) contains default values that identify the OAI URL, AS repository number, base URI for identifiers, and the public repository URL. [secrets.py](util/secrets_template.py) defines the data provider base URL, and API username and password.

The XML file will be written to 'staticrepo.xml' in the 'xml' directory:
```
../xml/staticrepo.xml
```
If duplicate URLs are found they are written to 'duplicates.txt' and omitted from the static repository:
```
../xml/duplicates.txt
```
There are options for running the script in dev or test mode. To see options:
```
 python buildxml.py -h
 ```
 ```
 usage: buildxml.py [-h] [-r RUNTYPE] [-n NUM_RECS]

options:
  -h, --help            show this help message and exit
  -r RUNTYPE, --runtype RUNTYPE
  -n NUM_RECS, --num_recs NUM_RECS
```
Default runtype is 'production' and includes all appropriate records in the repository. Any other value will cause the script to run in dev/test mode and the XML file will be written to the 'dev' folder. If no -n value is given, all records will be processed. If a negative -n value is given, 1000 records will be processed. Any other number defines the number of records to process.
```
../dev/staticrepo.xml
../dev/duplicates.txt
```
Running in dev/test mode does not affect the production XML output, which is the xml folder.

### Data Provider

The [OAI Data Provider](https://apps.library.caltech.edu/ead2dc/) is a web application written in Python 3 using the [Flask](https://flask.palletsprojects.com/en/3.0.x/) micro web framework. Installation of Flask will include dependent libraries, such as Jinja2 and werkzeug. No additional libraries are required.

The OAI Data Provider functionality provided by [oaidp.py](app/oaidp.py). Additional functions are imported from [aspace.py](app/aspace.py).

### Database

An SQLite3 database is used to store a log of OAI requests, information about collections (rewritten nightly when 'buildxml.py' runs), update dates, authorized users, and earliest date in the repository.
```
CREATE TABLE logs (date text, verb text, setname text, identifier text, datefrom text, dateuntil text);
CREATE TABLE collections (collno text, colltitle text, docount int, incl int, caltechlibrary int, internetarchive int, youtube int, other int, collid text, description text, typ text, aocount int default 0, last_edit text, type_text int, type_stillimage int, type_movingimage int, type_sound int, type_other int);
CREATE TABLE last_update (dt text, fn text);
CREATE TABLE user(username TEXT UNIQUE NOT NULL, role text);
CREATE TABLE dates (earliest TEXT);
```

### Default Values

Application defaults are stored in 'util/defaults.py' and 'util/secrets.py'. See [defaults_template.py](util/defaults_template.py) and [secrets_template](util/secrets_template.py) for guidance.

Global variables for [buildxml.py](util/buildxml.py) are listed in the "Global Configuration Section" at the top of that script. 

## License

Software produced by the Caltech Library is Copyright © 2026 California Institute of Technology.  This software is freely distributed under a BSD-style license.  Please see the [LICENSE](LICENSE) file for more information.


## References

* [OAI Static Repositories](http://www.openarchives.org/OAI/2.0/guidelines-static-repository.htm)
* [DCMI Metadata Terms](https://www.dublincore.org/specifications/dublin-core/dcmi-terms/)
* [Dublin Core Qualifiers](https://www.dublincore.org/specifications/dublin-core/dcmes-qualifiers/)
* [Guidelines for implementing DC in XML](https://www.dublincore.org/specifications/dublin-core/dc-xml-guidelines/2002-04-14/)


## Acknowledgments

This work was funded by the California Institute of Technology Library.