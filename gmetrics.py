#!/usr/bin/env python
import os
import glob
import graphitesend
import time

__author__ = 'Amar Tumballi'

PLUGIN_NAME = 'glusterfs'

# Change below two to handle data.
HOSTNAME = "local"
GRAPHITE_SERVER = "localhost"


print "Send Signal to GlusterFS..."
os.system ("ps aux | grep gluster | grep -v grep | awk '{ print $2 }' | xargs kill -USR2")

g = graphitesend.init (graphite_server=GRAPHITE_SERVER, prefix="gmetrics", system_name=HOSTNAME, group="gluster")

print "Started sending data to graphite ....\n"

# Idea is to provide a second for application to dump metrics
time.sleep(1)
timestamp = time.time()
for gfile in glob.glob("/tmp/glusterfs.*"):
    fd = open (gfile, "r")
    proc_id = "(null)"
    for line in fd.readlines():
        # Handle comments
        if "# glusterd" in line:
            break
        if "### BrickName: " in line:
            proc_id = line.split(":")[1].strip()
            continue
        if "(null)" == proc_id and "### MountName: " in line:
            proc_id = line.split (":")[1].strip()
            continue
        if "#" == line[0]:
            continue
        data = line.split(" ")
        # Send all data in single timestamp for better monitoring
        key = (("%s.%s") % (proc_id, data[0]))
        value = data[1].strip()
        g.send (key, value, timestamp)
    # Remove the file, so there won't be a repeat
    os.system ("rm %s" % gfile)
    print ("%s  [DONE] " % gfile)
