#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2017 Red Hat, Inc. <http://www.redhat.com/>
# This file is part of GlusterFS.
#
# This file is licensed to you under your choice of the GNU Lesser
# General Public License, version 3 or any later version (LGPLv3 or
# later), or the GNU General Public License, version 2 (GPLv2), in all
# cases as published by the Free Software Foundation.

import os
import glob
import time
from ConfigParser import ConfigParser
from argparse import ArgumentParser
import sys

import graphitesend


PLUGIN_NAME = 'glusterfs'

# Available metrics and respective metrics collection functions
AVAILABLE_METRICS = [
    "local_io",
    "local_utilization",
    "local_diskstats",
    "local_process",
]

metric_keys_diskstats = [
    "reads_completed",
    "reads_merged",
    "sectors_read",
    "time_spent_reading",
    "writes_completed",
    "writes_merged",
    "sectors_written",
    "time_spent_writing",
    "ios_currently_in_progress",
    "time_spent_doing_ios",
    "weighted_time_spent_doing_ios"
]

metric_keys_utilization = [
    "block_size",
    "blocks_total",
    "blocks_free",
    "blocks_avail",
    "inodes_total",
    "inodes_free",
    "inodes_avail"
]

metric_keys_processes = [
    "percentage_cpu",
    "percentage_memory",
    "resident_memory",
    "virtual_memory",
    "elapsed_time_sec",
]


def to_strlist(value):
    value = value.strip()
    if value == "":
        return []

    value = value.split(",")
    return [v.strip() for v in value]


def to_int(value):
    return int(value)


# Typecast to desired type after reading from conf file
TYPECAST_MAP = {
    "enabled_metrics": to_strlist,
    "interval": to_int
}

# Section name in Conf file
CONF_SECT = "settings"

# Global GraphiteSend object
g = None

# Default Config when config file is not passed
DEFAULT_CONFIG = {
    "interval": 15,
    "enabled_metrics": AVAILABLE_METRICS,
}


class Config(object):
    def __init__(self, config_file=None):
        self.config_file = config_file
        self.conf = None
        self.load()
        self.prev_mtime = None

    def get(self, name, default_value=None):
        if self.config_file is None:
            return DEFAULT_CONFIG.get(name, default_value)

        if self.conf is None:
            return default_value

        if self.conf.has_option(CONF_SECT, name):
            val = self.conf.get(CONF_SECT, name)
            typecast_func = TYPECAST_MAP.get(name, None)
            if typecast_func is not None:
                return typecast_func(val)

            return val
        else:
            return default_value

    def load(self):
        if self.config_file is None:
            return

        self.conf = ConfigParser()
        with open(self.config_file) as f:
            self.conf.readfp(f)

        # Store mtime of conf file for future comparison
        self.prev_mtime = os.lstat(self.config_file).st_mtime

    def reload(self):
        if self.config_file is None:
            return False

        st_mtime = os.lstat(self.config_file).st_mtime
        if self.prev_mtime is None or st_mtime > self.prev_mtime:
            self.load()
            return True

        return False


def local_io_metrics():
    global g
    print "Send Signal to GlusterFS..."
    os.system("ps aux | grep gluster | grep -v grep | "
              "awk '{ print $2 }' | xargs kill -USR2")

    # Idea is to provide a second for application to dump metrics
    time.sleep(1)

    timestamp = time.time()

    for gfile in glob.glob("/tmp/glusterfs.*"):
        with open(gfile) as f:
            proc_id = "(null)"
            for line in f:
                # Handle comments
                if "# glusterd" in line:
                    break

                if "### BrickName: " in line:
                    proc_id = line.split(":")[1].strip()
                    continue

                if "(null)" == proc_id and "### MountName: " in line:
                    proc_id = line.split(":")[1].strip()
                    continue

                if "#" == line[0]:
                    continue

                data = line.split(" ")
                # Send all data in single timestamp for better monitoring
                key = ".io.%s.%s" % (proc_id, data[0])
                value = data[1].strip()
                g.send(key, value, timestamp)

        # Remove the file, so there won't be a repeat
        os.remove(gfile)
        print("%s  [DONE] " % gfile)


def local_diskstats_metrics():
    # Local import, only if required
    from gluster.metrics import local_diskstats

    global g

    timestamp = time.time()
    for data in local_diskstats():
        key_pfx = ".diskstats.{volume}.{node_id}.{brick}.".format(**data)

        for k in metric_keys_diskstats:
            g.send(key_pfx + k, data[k], timestamp)


def local_utilization_metrics():
    # Local import, only if required
    from gluster.metrics import local_utilization

    global g

    timestamp = time.time()
    for data in local_utilization():
        key_pfx = ".utilization.{volume}.{node_id}.{brick}.".format(**data)

        for k in metric_keys_utilization:
            g.send(key_pfx + k, data[k], timestamp)


def local_process_metrics():
    # Local import, only if this metric enabled
    from gluster.metrics import local_processes

    global g

    timestamp = time.time()
    for data in local_processes():
        if data.get("name", "") == "glusterd":
            key_pfx = ".ps.{node_id}.glusterd.".format(**data)
        elif data.get("name", "") == "glusterfsd":
            key_pfx = (".ps.{volname}.{node_id}.{brick_path}."
                       "glusterfsd.".format(**data))
        else:
            # Not yet implemented tracking for other gluster processes
            continue

        for k in metric_keys_processes:
            g.send(key_pfx + k, data[k], timestamp)


def main():
    global g

    # Arguments Handling
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config-file", help="Config File")
    parser.add_argument("--graphite-server",
                        help="Graphite Server",
                        default="localhost")
    parser.add_argument("--hostname",
                        help="Hostname",
                        default="local")
    args = parser.parse_args()

    # Initialize Graphite Server
    g = graphitesend.init(graphite_server=args.graphite_server,
                          prefix="gmetrics",
                          system_name=args.hostname,
                          group="gluster",
                          fqdn_squash=True)

    # Load Config File
    conf = Config(args.config_file)

    enabled_metrics = conf.get("enabled_metrics")
    # If enabled_metrics list is empty enable all metrics
    if not enabled_metrics:
        enabled_metrics = AVAILABLE_METRICS

    # Metrics collection Loop
    while True:
        # Reloads only if config file is modified
        if conf.reload():
            print "Reloaded Config file"

            # Update the graphitesend prefix/group
            prefix_list = []
            prefix_list.append(conf.get("prefix", "gmetrics"))
            prefix_list.append(args.hostname)
            prefix_list.append(conf.get("group", "gluster"))

            g.formatter.prefix = '.'.join(prefix_list)

            # If Config is reloaded, get enabled metrics list again
            enabled_metrics = conf.get("enabled_metrics")
            # If enabled_metrics list is empty enable all metrics
            if not enabled_metrics:
                enabled_metrics = AVAILABLE_METRICS

        # TODO: Not yet Parallel to collect different metrics
        for m in enabled_metrics:
            metrics_func = globals().get(m + "_metrics", None)
            if metrics_func is not None:
                print "Sending %s metrics to Graphite" % m
                metrics_func()

        # Sleep till next collection interval
        time.sleep(conf.get("interval", 15))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print "Exiting.."
        sys.exit(1)
