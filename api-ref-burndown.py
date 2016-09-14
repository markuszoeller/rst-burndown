#!/usr/bin/env python

import argparse
import base64
import collections
import time
import glob
import os
import ConfigParser
import json
from multiprocessing import Pool
import re

import requests
from requests.auth import HTTPDigestAuth


config = ConfigParser.ConfigParser()
config.read('config.ini')

HEADLINE_FORMAT = "%-40s %12s %12s %12s %12s %12s\n"
HEADLINE_TITLES = ("File Name", "Description", "Deprecation", "Group/Type",
                   "Indentation", "Consistency")

# The format string for the special comments
COMMENT_FMT = "# %s\n"

# The comments pattern in Gerrit changes ('-' = the line got removed)
COMMENT_DIFF_REGEX = '-# needs:(.*)'

# The files to check for the special comments
FILE_REGEX = "%s/*.py"

# The file patterns in Gerrit changes
FILE_DIFF_REGEX = '--- a/nova/conf/(.*.py)$'

TOP = 'nova/nova/conf'

PROJECT_SITE = "https://review.openstack.org/changes/"
DIFF_QUERY = "%s/revisions/current/patch"
QUERY = "q=project:openstack/nova+file:^nova/conf/.*.py+NOT+age:7d"
ATTRS = ("&o=CURRENT_REVISION&o=ALL_COMMITS&o=ALL_FILES&o=LABELS"
         "&o=DETAILED_LABELS&o=DETAILED_ACCOUNTS")
URL = "%s?%s%s" % (PROJECT_SITE, QUERY, ATTRS)
DIFF_URL = PROJECT_SITE + DIFF_QUERY

PHASES = [
    'needs:fix_opt_description',
    'needs:check_deprecation_status',
    'needs:check_opt_group_and_type',
    'needs:fix_opt_description_indentation',
    'needs:fix_opt_registration_consistency',
    ]

counts = collections.OrderedDict()
for phase in PHASES:
    counts[phase] = []
counts['done'] = []

files = []




def _parse_content(resp, debug=False):
    # slice out the "safety characters"
    if resp.content[:4] == ")]}'":
        content = resp.content[5:]
        if debug:
            print("Response from Gerrit:\n")
            print(content)
        return json.loads(content)
    elif ('X-FYI-Content-Encoding' in resp.headers and
          resp.headers['X-FYI-Content-Encoding'] == 'base64'):
        return base64.b64decode(resp.content)
    else:
        print resp
        return resp.content


def fetch_data(url, debug=False):
    # read access doesn't need authentication
    resp = requests.get(url)
    return _parse_content(resp, debug)


def _http_process(change):
    diff = fetch_data(change['url'])
    files = []
    fname = None
    for line in diff.split('\n'):
        m = re.match(FILE_DIFF_REGEX, line)
        if m:
            fname = m.group(1)
        m = re.match(COMMENT_DIFF_REGEX, line)
        if m:
            tag = {'number': change['number'],
                   'filename': fname,
                   'tag': m.group(1)}
            files.append(tag)
    return files


def gather_reviews():
    data = fetch_data(URL)
    changes = []
    for change in data:
        if change['status'] != 'NEW':
            continue
        newchange = {}
        newchange['number'] = change['_number']
        newchange['url'] = DIFF_URL % change['id']
        changes.append(newchange)

    pool = Pool(processes=10)
    files = pool.map(_http_process, changes)
    relevant = []
    for f in files:
        if f:
            relevant.extend(f)
    return relevant


def update_review_list(files, updated):
    for fdata in files:
        updates = [x for x in updated if x['filename'] == fdata['filename']]
        for update in updates:
            what = "needs:%s" % update['tag']
            fdata[what] = update['number']


for fname in sorted(glob.glob(FILE_REGEX % TOP)):
    with open(fname) as f:
        fdata = {'filename': os.path.basename(fname)}
        content = f.readlines()
        done = True
        for key in PHASES:
            if COMMENT_FMT % key in content:
                fdata[key] = "TODO"
                done = False
                counts[key].append(fname)
            else:
                fdata[key] = u"\u2713"
        if done:
            counts['done'].append(fname)
        files.append(fdata)

relevant = gather_reviews()
update_review_list(files, relevant)

if not os.path.exists('data.csv'):
    with open("data.csv", "a") as f:
        f.write("%s,%s,%s,%s,%s,%s\n" % (
            'date',
            PHASES[0],
            PHASES[1],
            PHASES[2],
            PHASES[3],
            PHASES[4]))

with open("data.csv", "a") as f:
    f.write("%d,%d,%d,%d,%d,%d\n" % (
        int(time.time()),
        len(counts[PHASES[0]]),
        len(counts[PHASES[1]]),
        len(counts[PHASES[2]]),
        len(counts[PHASES[3]]),
        len(counts[PHASES[4]])))


with open("data.json", "w") as f:
    f.write(json.dumps(files))

with open("data.txt", "w") as f:
    f.write(HEADLINE_FORMAT % HEADLINE_TITLES)
    for fdata in files:
        f.write((HEADLINE_FORMAT % (
            fdata['filename'],
            fdata[PHASES[0]],
            fdata[PHASES[1]],
            fdata[PHASES[2]],
            fdata[PHASES[3]],
            fdata[PHASES[4]])).encode('utf8'))
